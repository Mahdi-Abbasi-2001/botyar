import { ViewTransition } from "react";

/** Wraps a page so moving between pages fades the old one out and lets the new one rise in
 *  (the CSS is in globals.css: .page-in / .page-out). Goes in each page, not the layout:
 *  layouts persist across navigations, so their enter/exit never fire. */
export function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <ViewTransition enter="page-in" exit="page-out" default="none">
      {children}
    </ViewTransition>
  );
}
