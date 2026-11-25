import { useState } from "react";
import logo from "../assets/madar-logo.png";
import "../dashboard/dashboard.css";
import "../student/student.css";
import "../parent/parent.css";
import StudentAgentView from "./StudentAgent.jsx";
import { ParentAgentView } from "./ParentAgent.jsx";

/** DEV-ONLY (`/preview/agent`): both pages on the mock data with no login and no backend, so the design can be
 *  reviewed on its own. App.jsx mounts this only when `import.meta.env.DEV` is true. */
export default function AgentPreview() {
  const [who, setWho] = useState(() => (new URLSearchParams(window.location.search).get("as") === "parent" ? "parent" : "student"));
  return (
    <div className="stu">
      <div className="ag-preview-bar">
        <img src={logo} alt="" height="22" />
        <span>معاينة وكيل مدار</span>
        <button type="button" aria-pressed={who === "student"} onClick={() => setWho("student")}>
          الطالب
        </button>
        <button type="button" aria-pressed={who === "parent"} onClick={() => setWho("parent")}>
          ولي الأمر
        </button>
      </div>
      <main className={"stu-body" + (who === "parent" ? " pp" : "")}>{who === "parent" ? <ParentAgentView /> : <StudentAgentView />}</main>
    </div>
  );
}
