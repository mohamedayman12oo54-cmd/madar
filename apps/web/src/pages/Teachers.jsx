import Page from "../components/Page.jsx";
import TeacherSection from "../components/TeacherSection.jsx";
import FastSessionSection from "../components/FastSessionSection.jsx";
import CTASection from "../components/CTASection.jsx";

export default function Teachers() {
  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">للمدرسين</div>
          <h2 className="h2">مدار للمعلّم المستقل.</h2>
          <p className="lead">أدوات تدريسك اليومية في نظام واحد — سريع أثناء الحصة، منظّم بعدها.</p>
        </div>
      </div>
      <TeacherSection />
      <FastSessionSection />
      <CTASection />
    </Page>
  );
}
