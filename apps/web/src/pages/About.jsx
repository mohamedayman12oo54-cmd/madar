import Page from "../components/Page.jsx";

export default function About() {
  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">عن مدار</div>
          <h2 className="h2">أكثر من منصة. طريقة أوضح للتدريس.</h2>
        </div>
      </div>
      <section className="section">
        <div className="wrap prose">
          <p>
            وُلد مدار من فكرة بسيطة: أن التعليم لا يدور حول الأدوات، بل حول الإنسان. المعلّم المستقل
            يستحق نظامًا واحدًا منظّمًا يجمع عمله كلّه، بدل تشتّته بين تطبيقات وأوراق.
          </p>
          <h3>ما نؤمن به</h3>
          <p>
            الوضوح قبل الزخم، والسرعة دون التضحية بالدقة، والذكاء الذي يساعد المعلّم ولا يحلّ محلّه.
            القرار يبقى دائمًا بيد الإنسان.
          </p>
          <h3>لمن نصنع مدار</h3>
          <p>
            للمعلّم الذي يدير بيئته التعليمية بنفسه، ولطلابه الذين يستحقون تجربة تعلّم واضحة ومحترمة
            لبياناتهم.
          </p>
        </div>
      </section>
    </Page>
  );
}
