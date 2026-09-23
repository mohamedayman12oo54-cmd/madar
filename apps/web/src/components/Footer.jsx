import { Link } from "react-router-dom";
import logo from "../assets/madar-logo.png";

export default function Footer() {
  return (
    <footer className="foot">
      <div className="wrap">
        <div className="fgr">
          <div className="fbrand">
            <Link to="/"><img src={logo} alt="مدار Madar" /></Link>
            <p>عالمك التعليمي، منظّمًا. بيئة تعليمية موحّدة — عربيّة أولًا.</p>
          </div>
          <div className="fcol">
            <h4>المنتج</h4>
            <Link to="/teachers">للمدرسين</Link>
            <Link to="/students">للطلاب</Link>
            <Link to="/features">المميزات</Link>
            <Link to="/how-it-works">كيف يعمل مدار</Link>
          </div>
          <div className="fcol">
            <h4>الشركة</h4>
            <Link to="/about">عن مدار</Link>
            <Link to="/contact">تواصل معنا</Link>
          </div>
          <div className="fcol">
            <h4>قانوني</h4>
            <Link to="/privacy">سياسة الخصوصية</Link>
            <Link to="/terms">شروط الاستخدام</Link>
          </div>
        </div>
        <div className="fbar">
          <span>© <span className="num">2026</span> مدار</span>
          <span>صُمّم بالعربية أولًا · RTL</span>
        </div>
      </div>
    </footer>
  );
}
