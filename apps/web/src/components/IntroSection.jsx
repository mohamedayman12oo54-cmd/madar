import Reveal from "./Reveal.jsx";

export default function IntroSection() {
  return (
    <section className="section intro" id="intro">
      <div className="wrap">
        <Reveal>
          <div className="kicker">فكرة مدار</div>
          <h2 className="h2">التعليم لا يدور حول الأدوات، بل حول الإنسان.</h2>
          <p className="lead">
            مدار يربط المعلّم والطالب والحضور والتسميع والمدفوعات والتقييم والذكاء الاستشاري في بيئة
            تعليمية واحدة متماسكة — بدل خمسة تطبيقات وورقة وجدول.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
