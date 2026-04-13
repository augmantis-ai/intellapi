// Next.js App Router - GET and POST handlers for /api/users

import { NextRequest, NextResponse } from 'next/server';

interface User {
  id: number;
  name: string;
  email: string;
}

/**
 * List all users
 */
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const limit = parseInt(searchParams.get('limit') || '10');
  const skip = parseInt(searchParams.get('skip') || '0');

  const users: User[] = [];
  return NextResponse.json(users);
}

/**
 * Create a new user
 */
export async function POST(request: NextRequest) {
  const body = await request.json();
  const user: User = {
    id: 1,
    name: body.name,
    email: body.email,
  };
  return NextResponse.json(user, { status: 201 });
}
