import { Link, useParams } from "react-router-dom";
import { MODULES } from "../modules.js";

export default function ModulePage() {
  const { modulePath } = useParams();
  const module = MODULES.find((item) => item.path === modulePath);

  if (!module) {
    return (
      <section>
        <h1>Page not found</h1>
        <Link to="/" className="button secondary">
          Back to dashboard
        </Link>
      </section>
    );
  }

  return (
    <section>
      <h1>{module.name}</h1>
      <p>{module.summary}</p>

      <div className="card">
        <strong>Status:</strong> planned for stage {module.stage}.
        <p className="muted">
          This screen is connected to the navigation so the layout and flow can be reviewed now. The
          working features are added with the stage {module.stage} backend endpoints.
        </p>
        <Link to="/" className="button secondary">
          Back to dashboard
        </Link>
      </div>
    </section>
  );
}
