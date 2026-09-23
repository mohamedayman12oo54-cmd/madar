import Page from "../components/Page.jsx";

export default function Privacy() {
  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">قانوني</div>
          <h2 className="h2">سياسة الخصوصية</h2>
          <p className="lead">هذا نصّ توضيحي مبدئي للواجهة، ويُستبدل لاحقًا بالنص القانوني المعتمد.</p>
        </div>
      </div>
      <section className="section">
        <div className="wrap prose">
          <h3>بياناتك</h3>
          <p>يعامل مدار بيانات الطلاب والمعلّمين كبيانات حسّاسة، وتبقى سجلات كل بيئة تعليمية معزولة ضمن نطاقها.</p>
          <h3>الوصول والصلاحيات</h3>
          <p>يُبنى الوصول على الهوية والدور والبيئة والملكية معًا، وتبقى ملاحظات المعلّم الخاصة خاصة.</p>
          <p style={{ color: "var(--soft)" }}>نصّ نموذجي — غير مُلزِم قانونيًا في هذه المرحلة.</p>
        </div>
      </section>
    </Page>
  );
}
