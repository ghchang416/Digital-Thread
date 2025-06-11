import ProjectDetailClient from "./pageClient";

type Props = {
  params: { id: string };
  searchParams: { name?: string };
};

// 1. async 키워드 제거
export default function ProjectDetailPage({ params, searchParams }: Props) {
  

  if (!params.id) {
    return <div>프로젝트 정보를 불러올 수 없습니다.</div>;
  }
  
  const project = {
    id: params.id,
    name: searchParams.name ?? "이름 없음",
  };
  return <ProjectDetailClient project={project}  />;
}