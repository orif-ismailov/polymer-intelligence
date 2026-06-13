import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Polymer Intelligence",
  description: "Market intelligence platform for the domestic polymer market",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
