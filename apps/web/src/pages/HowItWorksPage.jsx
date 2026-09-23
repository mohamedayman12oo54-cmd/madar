import Page from "../components/Page.jsx";
import HowItWorks from "../components/HowItWorks.jsx";
import FastSessionSection from "../components/FastSessionSection.jsx";
import CTASection from "../components/CTASection.jsx";

export default function HowItWorksPage() {
  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">كيف يعمل مدار</div>
          <h2 className="h2">من بيئة فارغة إلى تدريس واضح.</h2>
          <p className="lead">ست خطوات بسيطة تنقلك من الإعداد إلى المتابعة اليومية.</p>
        </div>
      </div>
      <HowItWorks />
      <FastSessionSection />
      <CTASection />
    </Page>
  );
}
