// Cursor: Middleware to protect Internal Dashboard routes from unauthenticated access (D-019)
import { type NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";

export async function middleware(request: NextRequest) {
  // Cursor: Create Supabase client inside middleware
  let supabaseResponse = NextResponse.next({
    request
  });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getSetCookie();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        }
      }
    }
  );

  // Cursor: Get current user session
  const {
    data: { user }
  } = await supabase.auth.getUser();

  // Cursor: Redirect unauthenticated users to /login when accessing /dashboard/**
  const pathname = request.nextUrl.pathname;
  if (pathname.startsWith("/dashboard") && !user) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Cursor: Allow authenticated users or login page access
  return supabaseResponse;
}

// Cursor: Config which routes to protect
export const config = {
  matcher: ["/dashboard", "/dashboard/:path*"]
};
