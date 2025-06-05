'use client';
import {useEffect, useState } from "react";
import ProjectList from "./components/ProjectList";
import SearchBar from "./components/SearchBar";
import ProjectNavBar from "./components/ProjectNavBar";

const PAGE_SIZE = 10;

export default function Page() {
  const [projects, setProjects] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchType, setSearchType] = useState("project_name");
  const [searchValue, setSearchValue] = useState("");
  const [loading, setLoading] = useState(false);

  // 1. 프로젝트 리스트 fetch
  useEffect(() => {
    async function fetchProjects() {
      setLoading(true);
      try {
        // 실제 API 주소, 쿼리 파라미터로 변경
        const params = new URLSearchParams({
          page: currentPage.toString(),
          size: PAGE_SIZE.toString(),
          type: searchType,
          value: searchValue,
        }).toString();
        const res = await fetch(`/api/projects?${params}`);
        //

        if (!res.ok) throw new Error("데이터 불러오기 실패");
        const data = await res.json();
        setProjects(data.projects);
        setTotalCount(data.totalCount);
      } catch (e) {
        setProjects([]);
        setTotalCount(0);
      }
      setLoading(false);
    }
    fetchProjects();
  }, [currentPage, searchType, searchValue]);


  // 실제로는 API 호출 등으로 검색 처리
  const handleSearch = (type: string, value: string) => {
    setSearchType(type);
    setSearchValue(value);
    setCurrentPage(1);
  };

  const handleDetail = (id: string) => {
    alert(`프로젝트 상세보기: ${id}`);
    // router.push(`/projects/${id}`); // 실제로는 상세 페이지 이동
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-white py-12">
      <div className="max-w-3xl mx-auto rounded-3xl bg-white/90  p-8">
        <h1 className="text-2xl font-bold text-blue-700 mb-8 text-center drop-shadow">
          Operation Manager – main
        </h1>
        <div className="mb-8 flex justify-end">
          <SearchBar onSearch={handleSearch} />
        </div>
        {loading ? (
          <div className="text-center text-gray-400 py-8">불러오는 중...</div>
        ) : (
          <ProjectList projects={projects} onDetail={handleDetail} />
        )}
        <ProjectNavBar
            totalCount={totalCount}
            currentPage={currentPage}
            onPageChange={setCurrentPage}
          />
        <div className="flex justify-center mt-8 text-gray-400">
          
        </div>
      </div>
    </main>
  );
}