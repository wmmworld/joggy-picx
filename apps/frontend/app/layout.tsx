import "./globals.css";
import Providers from "../components/Providers";

// Cursor: Root layout for internal app (Server Component)
export const metadata = {
  title: "Joggy-PicX — Internal Dashboard",
  description: "Admin / Staff dashboard for Joggy-PicX"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
