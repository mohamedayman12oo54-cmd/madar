import { Link } from "react-router-dom";
import { BookOpen, FileText, NotebookPen } from "lucide-react";
import DocumentOpener from "../components/DocumentOpener.jsx";
import { fmtDate } from "../lib/dates.js";
import { formatBytes } from "../lib/files.js";
import { studentApi } from "../lib/studentApi.js";

/** A PDF or a summary the teacher published. One look tells what it is (icon + label), when it came, and
 *  there is one obvious button. A PDF opens through a short-lived ticket; a summary on its own reading page. */
export default function MaterialCard({ item }) {
  const pdf = item.kind === "pdf";
  const Icon = pdf ? FileText : NotebookPen;
  const meta = [pdf ? "ملف PDF" : "ملخص", pdf ? formatBytes(item.file_size) : "", item.published_at ? fmtDate(item.published_at) : ""]
    .filter(Boolean)
    .join(" • ");
  return (
    <article className={"mat-card " + (pdf ? "is-pdf" : "is-summary")}>
      <span className="mat-card-icon" aria-hidden="true">
        <Icon size={22} />
      </span>
      <div className="mat-card-text">
        <h3>{item.title}</h3>
        {item.description && <p>{item.description}</p>}
        <small>{meta}</small>
      </div>
      <div className="mat-card-go">
        {pdf ? (
          <DocumentOpener getTicket={() => studentApi.documentTicket(item.id)} label="فتح الملف" />
        ) : (
          <Link to={`/learn/materials/${item.id}`} className="abtn abtn-primary">
            <BookOpen size={15} /> قراءة الملخص
          </Link>
        )}
      </div>
    </article>
  );
}
