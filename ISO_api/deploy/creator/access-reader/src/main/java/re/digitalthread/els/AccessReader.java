package re.digitalthread.els;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.healthmarketscience.jackcess.*;
import java.io.File;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.time.temporal.TemporalAccessor;
import java.util.*;

/** Read table data only. No SQL engine, macro execution, or linked-file access. */
public final class AccessReader {
    private static final Gson JSON = new GsonBuilder().serializeNulls().disableHtmlEscaping().create();
    private static final PrintWriter OUT = new PrintWriter(System.out, true, StandardCharsets.UTF_8);
    private static final Set<String> TABLES = Set.of("part_info", "operation_info", "operation_machining",
        "machine_milling", "tool_milling", "part_file", "machine_file", "tool_file");
    private static final Set<DataType> SCALARS = Set.of(DataType.TEXT, DataType.MEMO, DataType.BOOLEAN,
        DataType.BYTE, DataType.INT, DataType.LONG, DataType.FLOAT, DataType.DOUBLE, DataType.MONEY,
        DataType.NUMERIC, DataType.SHORT_DATE_TIME, DataType.GUID, DataType.BIG_INT);

    private static void emit(Map<String, Object> value) {
        OUT.println(JSON.toJson(value));
        if (OUT.checkError()) throw new IllegalStateException("OUTPUT_CLOSED");
    }

    public static void main(String[] args) {
        if (args.length == 1 && args[0].equals("--version")) {
            emit(Map.of("kind", "version", "protocol", 1, "readerVersion", "jackcess-4.0.8/els-1"));
            return;
        }
        if (args.length != 2) { System.exit(2); return; }
        try {
            int limit = Integer.parseInt(args[1]);
            if (limit < 1 || limit > 100000) throw new IllegalArgumentException();
            read(new File(args[0]), limit);
        } catch (Exception ex) {
            // Never return paths, connection strings, original values, or Java traces.
            String code = ex instanceof LimitException ? "ROW_LIMIT" : "ACCESS_READ_FAILED";
            emit(Map.of("kind", "error", "code", code));
            System.exit(2);
        }
    }

    private static void read(File file, int limit) throws Exception {
        try (Database db = new DatabaseBuilder(file).setReadOnly(true).setAutoSync(false).open()) {
            // Defense in depth: no linked table may open an external file/database.
            db.setLinkResolver((ignored, path) -> { throw new java.io.IOException("LINKED_TABLE_BLOCKED"); });
            db.setDateTimeType(DateTimeType.LOCAL_DATE_TIME);
            emit(Map.of("kind", "database", "protocol", 1, "readerVersion", "jackcess-4.0.8/els-1",
                "format", db.getFileFormat().name()));
            int total = 0;
            for (TableMetaData metadata : db.newTableMetaDataIterable()) {
                String name = metadata.getName();
                if (!TABLES.contains(name.toLowerCase(Locale.ROOT))) continue;
                if (metadata.isLinked()) {
                    emit(Map.of("kind", "diagnostic", "table", name, "code", "LINKED_TABLE_UNAVAILABLE"));
                    continue;
                }
                Table table = metadata.open(db);
                List<Map<String, Object>> columns = new ArrayList<>();
                List<String> readable = new ArrayList<>();
                for (Column c : table.getColumns()) {
                    boolean supported = SCALARS.contains(c.getType()) && !c.isCalculated();
                    columns.add(Map.of("name", c.getName(), "type", c.getType().name(), "readable", supported));
                    if (supported) readable.add(c.getName());
                }
                List<String> pk = new ArrayList<>();
                for (Index index : table.getIndexes()) if (index.isPrimaryKey()) {
                    for (Index.Column column : index.getColumns()) pk.add(column.getName());
                }
                emit(Map.of("kind", "table", "name", name, "columns", columns, "primaryKey", pk));
                int count = 0;
                for (Row row : table.newCursor().toCursor().newIterable().setColumnNames(readable)) {
                    if (++total > limit) throw new LimitException();
                    Map<String, Object> values = new LinkedHashMap<>();
                    for (String column : readable) {
                        Object value = row.get(column);
                        if (value instanceof TemporalAccessor || value instanceof UUID) value = value.toString();
                        if (value != null && !(value instanceof String || value instanceof Number || value instanceof Boolean)) {
                            throw new IllegalArgumentException("UNSUPPORTED_VALUE");
                        }
                        if (value instanceof String && ((String)value).length() > 65536) throw new LimitException();
                        values.put(column, value);
                    }
                    emit(Map.of("kind", "row", "table", name, "values", values));
                    count++;
                }
                emit(Map.of("kind", "tableEnd", "table", name, "count", count));
            }
            emit(Map.of("kind", "complete", "rowCount", total));
        }
    }

    private static final class LimitException extends RuntimeException { }
}
