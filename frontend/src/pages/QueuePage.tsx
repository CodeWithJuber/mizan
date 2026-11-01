/** Queue: background work waiting for and running on workers. */
import { QueueDashboard } from "../components/QueueDashboard";
import { useApi } from "../hooks/useApi";

export default function QueuePage() {
  const api = useApi();
  return (
    <div className="page-body">
      <QueueDashboard api={api} />
    </div>
  );
}
