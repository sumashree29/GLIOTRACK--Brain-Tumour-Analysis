import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import ThemeInitializer from "@/components/layout/ThemeInitializer";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = { 
  title:       "GLIOTRACK — Brain Tumour Analysis",
  description: "GLIOTRACK: AI-assisted brain tumour segmentation, RANO classification, and longitudinal reporting.",
  robots:      "noindex, nofollow",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="antialiased" style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}>
        <ThemeInitializer />
        {children}
      </body>
    </html>
  );
}