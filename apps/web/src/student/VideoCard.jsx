import { Link } from "react-router-dom";
import { Play } from "lucide-react";

/** The student's video "message": title, description, and a «زيارة» button
 *  that opens the video's own page. Used on the home page and the list. */
export default function VideoCard({ video }) {
  return (
    <article className="video-msg">
      <div className="video-msg-text">
        <h3>{video.title}</h3>
        {video.description && <p>{video.description}</p>}
      </div>
      <Link to={`/learn/videos/${video.id}`} className="mini-btn is-primary video-msg-go">
        <Play size={13} /> زيارة
      </Link>
    </article>
  );
}
