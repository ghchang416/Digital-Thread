import ProjectDetailClient from "./pageClient";

type Props = {
  params : { 
    id : string
  }
}

//서버 컴포넌트에서는 내 자신을 가리키고 있지 않기 때문에 풀경로를 줘야 목업 API를 호출할 수 있음.
//그래서 추가한 부분
const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';

export default async function ProjectDetailPage({ params }: Props) {

  const project_id = params.id;

  //실제 API를 호출하는 부분 - 프로젝트 상세 페이지 불러올 때, 이 URL을 수정해주면 됨
  const res = await fetch(`${BASE_URL}/api/projects/${project_id}`, { cache: "no-store" });
  //

  if (!res.ok) {
    return <div>프로젝트 정보를 불러올 수 없습니다.</div>;
  }
  const project = await res.json();

  return <ProjectDetailClient project={project}/>;
}