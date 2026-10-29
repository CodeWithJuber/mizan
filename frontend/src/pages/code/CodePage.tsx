/** /code lists the person's projects; /code/:projectId opens one beside its chat. */
import { useParams } from "react-router-dom";
import ProjectList from "./ProjectList";
import ProjectView from "./ProjectView";

export default function CodePage() {
  const { projectId } = useParams();
  return projectId ? <ProjectView key={projectId} projectId={projectId} /> : <ProjectList />;
}
