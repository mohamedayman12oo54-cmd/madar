import Page from "../components/Page.jsx";
import Hero from "../components/Hero.jsx";
import IntroSection from "../components/IntroSection.jsx";
import TeacherSection from "../components/TeacherSection.jsx";
import StudentSection from "../components/StudentSection.jsx";
import FastSessionSection from "../components/FastSessionSection.jsx";
import AISection from "../components/AISection.jsx";
import FeaturesSection from "../components/FeaturesSection.jsx";
import HowItWorks from "../components/HowItWorks.jsx";
import SecuritySection from "../components/SecuritySection.jsx";
import CTASection from "../components/CTASection.jsx";

export default function Home({ ready }) {
  return (
    <Page>
      <Hero ready={ready} />
      <IntroSection />
      <TeacherSection />
      <StudentSection />
      <FastSessionSection />
      <AISection />
      <FeaturesSection />
      <HowItWorks />
      <SecuritySection />
      <CTASection />
    </Page>
  );
}
