import { useEffect, useState } from "react";
import QRCode from "qrcode";

/**
 * Renders a QR code as an <img> backed by a data: URL.
 *
 * An image can never run script, so — unlike injecting generated SVG markup
 * with dangerouslySetInnerHTML — nothing the encoded text contains can ever
 * become executable, now or after a future library change.
 */
export default function QrImage({ text, size = 220, alt, className, fallback = null }) {
  const [src, setSrc] = useState("");

  useEffect(() => {
    let alive = true;
    setSrc("");
    if (!text) return undefined;
    QRCode.toDataURL(String(text), { margin: 1, width: size * 2, errorCorrectionLevel: "M" })
      .then((url) => alive && setSrc(url))
      .catch(() => alive && setSrc(""));
    return () => {
      alive = false;
    };
  }, [text, size]);

  if (!src) return fallback;
  return (
    <img className={className} src={src} alt={alt} width={size} height={size} draggable={false} />
  );
}
