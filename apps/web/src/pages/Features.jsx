import Page from "../components/Page.jsx";
import FeaturesSection from "../components/FeaturesSection.jsx";
import AISection from "../components/AISection.jsx";
import CTASection from "../components/CTASection.jsx";

export default function Features() {
  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">المميزات</div>
          <h2 className="h2">كل ما تحتاجه، في نظام واحد.</h2>
          <p className="lead">من إدارة الطلاب إلى الذكاء الاستشاري — متماسكًا ومتّصلًا.</p>
        </div>
      </div>
      <FeaturesSection />
      <AISection />
      <CTASection />
    </Page>
  );
}
