import Image from "next/image";

import { APP_NAME, LOGO_HEIGHT, LOGO_SRC, LOGO_WIDTH } from "@/lib/constants";

/**
 * The logo is a JPEG on white, so it always sits on a white tile; that keeps it correct in dark
 * mode without editing the supplied file.
 */
export function Logo({ height = 32, priority = false }: { height?: number; priority?: boolean }) {
  const width = Math.round((height * LOGO_WIDTH) / LOGO_HEIGHT);
  return (
    <span className="inline-flex w-fit items-center rounded-sm bg-white px-2 py-1">
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
