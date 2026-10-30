import Image from "next/image";

import { APP_NAME, LOGO_HEIGHT, LOGO_SRC, LOGO_WIDTH } from "@/lib/constants";

/**
 * The logo is a transparent PNG with dark lettering, so it sits directly on the page in light mode
 * and on a white tile in dark mode (see `.logo-tile` in globals.css).
 */
export function Logo({ height = 32, priority = false }: { height?: number; priority?: boolean }) {
  const width = Math.round((height * LOGO_WIDTH) / LOGO_HEIGHT);
  return (
    <span className="logo-tile inline-flex w-fit items-center">
      <Image
        src={LOGO_SRC}
        alt={`${APP_NAME} by Vezapp`}
        width={width}
        height={height}
        priority={priority}
        style={{ height, width: "auto" }}
      />
    </span>
  );
}
