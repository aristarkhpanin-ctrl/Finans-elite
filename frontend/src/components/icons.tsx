import type { ReactNode, SVGProps } from "react";

/**
 * Набор иконок редизайна (Р6): инлайн-SVG 24×24, stroke 1.7,
 * цвет — currentColor (наследуется от текста).
 */
export interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

function Icon({ size = 18, children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const IconUser = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="8" r="3.6" />
    <path d="M4.8 19.4c1.4-2.9 4.1-4.4 7.2-4.4s5.8 1.5 7.2 4.4" />
  </Icon>
);

export const IconUsers = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="9" cy="8.5" r="3.2" />
    <path d="M2.8 19c1.2-2.6 3.5-4 6.2-4s5 1.4 6.2 4" />
    <path d="M16 5.6a3.2 3.2 0 0 1 0 5.8M18.5 15.4c1.3.7 2.3 1.9 2.9 3.6" />
  </Icon>
);

export const IconMail = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="5.5" width="18" height="13" rx="2.5" />
    <path d="m4 7.5 8 5.5 8-5.5" />
  </Icon>
);

export const IconLock = (p: IconProps) => (
  <Icon {...p}>
    <rect x="5" y="10.5" width="14" height="9.5" rx="2.5" />
    <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" />
    <circle cx="12" cy="15.2" r="1.2" fill="currentColor" stroke="none" />
  </Icon>
);

export const IconEye = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="2.8" />
  </Icon>
);

export const IconEyeOff = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4.5 8.6C3.2 9.9 2.5 12 2.5 12S6 18.2 12 18.2c1.3 0 2.5-.3 3.6-.8M9.4 6.2c.8-.3 1.7-.4 2.6-.4 6 0 9.5 6.2 9.5 6.2s-.9 1.6-2.5 3.1" />
    <path d="M9.9 9.9a2.8 2.8 0 0 0 4 4" />
    <path d="m4 4 16 16" />
  </Icon>
);

export const IconBuilding = (p: IconProps) => (
  <Icon {...p}>
    <rect x="4.5" y="3.5" width="11" height="17" rx="1.5" />
    <path d="M15.5 9.5h3a1.5 1.5 0 0 1 1.5 1.5v9.5h-4.5M8 7.5h1.5M10.5 7.5H12M8 11h1.5M10.5 11H12M8 14.5h1.5M10.5 14.5H12" />
    <path d="M2.8 20.5h18.4" />
  </Icon>
);

export const IconTrash = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 6.5h16M9 6.5V4.8A1.3 1.3 0 0 1 10.3 3.5h3.4A1.3 1.3 0 0 1 15 4.8v1.7" />
    <path d="M6 6.5 6.8 19a1.8 1.8 0 0 0 1.8 1.7h6.8a1.8 1.8 0 0 0 1.8-1.7L18 6.5" />
    <path d="M10 10.5v6M14 10.5v6" />
  </Icon>
);

export const IconCopy = (p: IconProps) => (
  <Icon {...p}>
    <rect x="8.5" y="8.5" width="12" height="12" rx="2.5" />
    <path d="M5.5 15.5h-1a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
  </Icon>
);

export const IconSearch = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m15.8 15.8 4.7 4.7" />
  </Icon>
);

export const IconGrid = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
  </Icon>
);

export const IconRows = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4" width="17" height="6.5" rx="1.5" />
    <rect x="3.5" y="13.5" width="17" height="6.5" rx="1.5" />
  </Icon>
);

export const IconPrint = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 8V3.5h10V8" />
    <rect x="3.5" y="8" width="17" height="9" rx="2" />
    <path d="M7 13.5h10v7H7z" />
  </Icon>
);

export const IconDownload = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5v11M7.5 10.5 12 15l4.5-4.5" />
    <path d="M4 16.5v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </Icon>
);

export const IconPlus = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const IconChart = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 4v15.5A0.5 0.5 0 0 0 4.5 20H20" />
    <path d="m7.5 14.5 3.5-4 3 2.5 4.5-6" />
  </Icon>
);

export const IconBox = (p: IconProps) => (
  <Icon {...p}>
    <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
    <path d="m4.4 7.8 7.6 4.3 7.6-4.3M12 12.1V21" />
  </Icon>
);

export const IconCart = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="9.5" cy="19.5" r="1.4" />
    <circle cx="17.5" cy="19.5" r="1.4" />
    <path d="M3 4h2.2l2.4 11.2a1.5 1.5 0 0 0 1.5 1.2h8.2a1.5 1.5 0 0 0 1.5-1.2L20.5 8H6.1" />
  </Icon>
);

export const IconBriefcase = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="7.5" width="17" height="12.5" rx="2" />
    <path d="M9 7.5V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.5M3.5 12.5h17" />
  </Icon>
);

export const IconWarning = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4 2.8 19.5h18.4L12 4Z" />
    <path d="M12 10v4.2" />
    <circle cx="12" cy="16.8" r="0.9" fill="currentColor" stroke="none" />
  </Icon>
);

export const IconCheck = (p: IconProps) => (
  <Icon {...p}>
    <path d="m4.5 12.5 5 5L19.5 7" />
  </Icon>
);

export const IconX = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
);

export const IconArrowRight = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 12h16M13.5 5.5 20 12l-6.5 6.5" />
  </Icon>
);

export const IconChevronDown = (p: IconProps) => (
  <Icon {...p}>
    <path d="m6 9.5 6 6 6-6" />
  </Icon>
);

export const IconBurger = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 6.5h16M4 12h16M4 17.5h16" />
  </Icon>
);

export const IconLogout = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14.5 4h-8A2.5 2.5 0 0 0 4 6.5v11A2.5 2.5 0 0 0 6.5 20h8" />
    <path d="M10 12h10.5M17 8.5l3.5 3.5-3.5 3.5" />
  </Icon>
);

export const IconSettings = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 13.5a7.6 7.6 0 0 0 0-3l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-2.6-1.5L14 2.5h-4L9.6 5a7.6 7.6 0 0 0-2.6 1.5l-2.4-1-2 3.4 2 1.6a7.6 7.6 0 0 0 0 3l-2 1.6 2 3.4 2.4-1a7.6 7.6 0 0 0 2.6 1.5l.4 2.5h4l.4-2.5a7.6 7.6 0 0 0 2.6-1.5l2.4 1 2-3.4-2-1.6Z" />
  </Icon>
);

export const IconInfo = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5" />
    <circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none" />
  </Icon>
);

export const IconFactory = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 20V9l6 4V9l6 4V6l6 3v11z" />
    <path d="M3 20h18" />
  </Icon>
);

export const IconLand = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2.5 19.5h19" />
    <path d="m4 19.5 5-8 3.5 5.5 3-4.5 4.5 7" />
    <circle cx="17" cy="6.5" r="2" />
  </Icon>
);

export const IconFolder = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 6.5A2 2 0 0 1 5.5 4.5h4l2 2.5h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-11Z" />
  </Icon>
);
