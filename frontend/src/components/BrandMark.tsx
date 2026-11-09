import { useState } from "react";
/** The supplied logo is decorative beside the accessible Veriora wordmark. */
export function BrandMark() {
  const [loaded, setLoaded] = useState(false);
  return (
    <span className="brand-mark" aria-hidden="true">
      <img
        src="/logo.png"
        alt=""
        width="28"
        height="28"
        hidden={!loaded}
        onLoad={() => setLoaded(true)}
        onError={() => setLoaded(false)}
      />
      <span hidden={loaded} className="brand-fallback">
        V
      </span>
    </span>
  );
}
