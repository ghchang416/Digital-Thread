package re.digitalthread.els;

import com.healthmarketscience.jackcess.*;
import java.nio.file.*;
import java.math.BigDecimal;

/** Synthetic data only. Never opens or modifies a supplied customer database. */
public final class GenerateFixtures {
    private static ColumnBuilder text(String name) { return new ColumnBuilder(name, DataType.TEXT).setLengthInUnits(255); }
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]);
        Files.createDirectories(root);
        for (String name : new String[]{"synthetic.mdb", "synthetic.accdb", "linked.accdb", "unsupported.accdb"}) {
            if (Files.exists(root.resolve(name))) throw new IllegalStateException("Refuse to overwrite fixture");
        }
        create(root.resolve("synthetic.mdb"), Database.FileFormat.V2000);
        create(root.resolve("synthetic.accdb"), Database.FileFormat.V2010);
        try (Database db = DatabaseBuilder.create(Database.FileFormat.V2010, root.resolve("linked.accdb").toFile())) {
            db.createLinkedTable("Operation_Machining", "/not-allowed/customer.accdb", "Operation_Machining");
        }
        try (Database db = DatabaseBuilder.create(Database.FileFormat.V2007, root.resolve("unsupported.accdb").toFile())) {
            new TableBuilder("Part_Info").addColumn(text("Part_No")).toTable(db);
        }
    }
    private static void create(Path path, Database.FileFormat format) throws Exception {
        if (Files.exists(path)) throw new IllegalStateException("Refuse to overwrite fixture");
        try (Database db = DatabaseBuilder.create(format, path.toFile())) {
            Table parts = new TableBuilder("Part_Info")
                .addColumn(text("Part_No")).addColumn(text("Part_Rev")).addColumn(text("Part_Name"))
                .addColumn(text("Part_Material")).addColumn(text("Spec_재질"))
                .setPrimaryKey("Part_No", "Part_Rev").toTable(db);
            parts.addRow("P-001", "01", "합성 부품", "AL6061", null);
            parts.addRow("P-001", "02", "합성 부품 개정", "AL6061", "");
            parts.addRow("P-002", "01", "다른 부품", "STEEL", "TEST");
            Table operations = new TableBuilder("Operation_Info")
                .addColumn(text("Part_No")).addColumn(text("Part_Rev")).addColumn(text("Op_No"))
                .addColumn(text("공정 Type")).addColumn(text("설비코드")).addColumn(text("설비번호"))
                .setPrimaryKey("Part_No", "Part_Rev", "Op_No").toTable(db);
            operations.addRow("P-001", "01", "010", "MILLING", "MC", "001");
            operations.addRow("P-001", "01", "020", "TURNING", "MC", "002");
            operations.addRow("P-001", "02", "010", "MILLING", "MC", "001");
            operations.addRow("P-002", "01", "010", "MILLING", "MC", "001");
            Table steps = new TableBuilder("Operation_Machining")
                .addColumn(new ColumnBuilder("Operation_Machining_SN", DataType.LONG))
                .addColumn(text("Part_No")).addColumn(text("Part_Rev")).addColumn(text("Op_No"))
                .addColumn(text("PGMNO")).addColumn(text("REVNO"))
                .addColumn(new ColumnBuilder("SEQNO", DataType.LONG)).addColumn(text("TOOLNO"))
                .addColumn(text("DESC")).addColumn(new ColumnBuilder("SPINDLE_01", DataType.DOUBLE))
                .addColumn(new ColumnBuilder("SPINDLE_02", DataType.DOUBLE))
                .addColumn(new ColumnBuilder("FEED_01", DataType.DOUBLE))
                .addColumn(new ColumnBuilder("TEST_BOOLEAN", DataType.BOOLEAN))
                .addColumn(new ColumnBuilder("TEST_DECIMAL", DataType.NUMERIC).setPrecision(28).setScale(6))
                .setPrimaryKey("Operation_Machining_SN").toTable(db);
            steps.addRow(1, "P-001", "01", "010", "100", "A", 10, "001", "황삭", 6000d, null, 800d, false, new BigDecimal("123456789012345678.123456"));
            steps.addRow(2, "P-001", "01", "010", "100", "A", 20, "001", "", 0d, -1000d, 0d, true, BigDecimal.ZERO);
            steps.addRow(3, "P-001", "01", "010", "200", "B", 10, "002", "다른 프로그램", 3000d, 5000d, 500d, false, null);
            steps.addRow(4, "P-001", "02", "010", "100", "A", 10, "002", "가공", 3000d, null, 600d, false, null);
            steps.addRow(5, "P-002", "01", "010", "100", "A", 10, "003", "다른 파트", 3000d, null, 600d, false, null);
            Table machines = new TableBuilder("Machine_Milling").addColumn(text("설비코드"))
                .addColumn(text("설비번호")).addColumn(text("설비명")).setPrimaryKey("설비코드", "설비번호").toTable(db);
            machines.addRow("MC", "001", "합성 5축 장비");
            new TableBuilder("Tool_Milling").addColumn(text("공구번호")).addColumn(text("공구사양"))
                .setPrimaryKey("공구번호").toTable(db);
            new TableBuilder("Part_File").addColumn(text("Part_No")).addColumn(text("Part_Rev"))
                .addColumn(text("File_Path")).toTable(db).addRow("P-001", "01", "\\\\unavailable\\share\\program.nc");
            // A non-allowlisted table is never exported, even if it contains data.
            new TableBuilder("Private_Costs").addColumn(text("value")).toTable(db).addRow("NOT_EXPORTED");
        }
    }
}
