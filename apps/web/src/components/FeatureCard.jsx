import Icon from "./Icon.jsx";

export default function FeatureCard({ icon, title }) {
  return (
    <div className="fcell">
      <div className="ic"><Icon name={icon} size={20} /></div>
      <span>{title}</span>
    </div>
  );
}
