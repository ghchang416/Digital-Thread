import { NextResponse } from "next/server";

const ALL_PROJECTS = [
  { id: "6822cce1f4e19c7ff68ff63a", name: "Test_project1" },
  { id: "6822cce1f4e19c7ff68ff87a", name: "Test_project2" },
  { id: "6822cce1f4e19c7ff62f36a", name: "Test_project3" },
  { id: "6822cce1f4e19c7ff68ff63b", name: "Test_project4" },
  { id: "6822cce1f4e19c7ff68ff63c", name: "Test_project5" },
  { id: "6822cce1f4e19c7ff68ff63d", name: "Test_project6" },
  { id: "6822cce1f4e19c7ff68ff63e", name: "Test_project7" },
  { id: "6822cce1f4e19c7ff68ff63f", name: "Test_project8" },
  { id: "6822cce1f4e19c7ff68ff640", name: "Test_project9" },
  { id: "6822cce1f4e19c7ff68ff641", name: "Test_project10" },
  { id: "6822cce1f4e19c7ff68ff642", name: "Test_project11" },
  { id: "6822cce1f4e19c7ff68ff643", name: "Test_project12" },
  { id: "6822cce1f4e19c7ff68ff644", name: "Test_project13" },
  // ...더 추가 가능
];

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = parseInt(searchParams.get("page") || "1", 10);
  const size = parseInt(searchParams.get("size") || "10", 10);
  const type = searchParams.get("type") || "project_name";
  const value = (searchParams.get("value") || "").trim();

  let filtered = ALL_PROJECTS;
  if (value) {
    filtered = filtered.filter((p) =>
      type === "project_id"
        ? p.id.includes(value)
        : p.name.includes(value)
    );
  }

  const totalCount = filtered.length;
  const startIdx = (page - 1) * size;
  const endIdx = startIdx + size;
  const paged = filtered.slice(startIdx, endIdx);

  return NextResponse.json({
    projects: paged,
    totalCount,
  });
}