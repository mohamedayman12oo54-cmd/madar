import Page from "../components/Page.jsx";
import StudentSection from "../components/StudentSection.jsx";
import CTASection from "../components/CTASection.jsx";

export default function Students() {
  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">للطلاب</div>
          <h2 className="h2">تعلّم أوضح، رحلة أهدأ.</h2>
          <p className="lead">كل ما يخصّ الطالب في مكان واحد — للهاتف أولًا.</p>
        </div>
      </div>
      <StudentSection />
      <CTASection />
    </Page>
  );
}
