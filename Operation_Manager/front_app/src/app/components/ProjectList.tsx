import ProjectListItem from "./ProjectListItem";

type Project = {
  id: string;
  name: string;
};

type ProjectListProps = {
  projects: Project[];
  onDetail: (id: string) => void;
};

export default function ProjectList({ projects, onDetail }: ProjectListProps) {
  return (
    <div className="grid gap-4">
      {projects.map((p) => (
        <ProjectListItem
          key={p.id}
          id={p.id}
          name={p.name}
        />
      ))}
    </div>
  );
}