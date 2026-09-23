import Page from "../components/Page.jsx";

export default function Terms() {
  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">قانوني</div>
          <h2 className="h2">شروط الاستخدام</h2>
          <p className="lead">هذا نصّ توضيحي مبدئي للواجهة، ويُستبدل لاحقًا بالنص القانوني المعتمد.</p>
        </div>
      </div>
      <section className="section">
        <div className="wrap prose">
          <h3>الاستخدام</h3>
          <p>باستخدامك مدار، توافق على استعماله ضمن الغرض التعليمي المخصّص له.</p>
          <h3>المسؤولية</h3>
          <p>يبقى المعلّم صاحب القرار النهائي في بيئته التعليمية، والذكاء في مدار استشاري لا أكثر.</p>
          <p style={{ color: "var(--soft)" }}>نصّ نموذجي — غير مُلزِم قانونيًا في هذه المرحلة.</p>
        </div>
      </section>
    </Page>
  );
}
