export default function SectionTitle({ kicker, title, lead, style }) {
  return (
    <div style={style}>
      {kicker && <div className="kicker">{kicker}</div>}
      <h2 className="h2">{title}</h2>
      {lead && <p className="lead">{lead}</p>}
    </div>
  );
}
