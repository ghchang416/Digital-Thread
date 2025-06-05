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

type Params = { params: { id: string } };

export async function GET(request: Request, context: {params:Promise<{id:string}>} ) {
    const params = await context.params; 
    const {id} = params;

    const project = ALL_PROJECTS.find((p) => p.id === id);

    if (!project) {
        return NextResponse.json(
        { message: "Project not found" },
        { status: 404 }
        );
    }

    return NextResponse.json(project);
}