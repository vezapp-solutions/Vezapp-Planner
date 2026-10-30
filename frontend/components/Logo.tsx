import Image from "next/image";

import { APP_NAME, LOGO_DARK_SRC, LOGO_HEIGHT, LOGO_SRC, LOGO_WIDTH } from "@/lib/constants";

/**
 * Two transparent PNGs of the same logo: charcoal lettering for light mode and white lettering for
 * dark mode. CSS shows one of them (`.logo-on-light` / `.logo-on-dark` in globals.css).
 */
export function Logo({ height = 32, priority = false }: { height?: number; priority?: boolean }) {
  const width = Math.round((height * LOGO_WIDTH) / LOGO_HEIGHT);
  const alt = `${APP_NAME} by Vezapp`;
  const style = { height, width: "auto" } as const;
  return (
    <span className="inline-flex w-fit items-center">
      <Image src={LOGO_SRC} alt={alt} className="logo-on-light" width={width} height={height} priority={priority} style={style} />
      <Image src={LOGO_DARK_SRC} alt={alt} className="logo-on-dark" width={width} height={height} priority={priority} style={style} />
    </span>
  );
}
