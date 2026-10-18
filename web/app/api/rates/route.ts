import { NextRequest, NextResponse } from "next/server";
import { getRateRecords } from "@/lib/api/data";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const search = searchParams.get("search") || undefined;
    const billing_code = searchParams.get("billing_code") || undefined;
    const specialty = searchParams.get("specialty") || undefined;
    const address_status = searchParams.get("address_status") || undefined;
    const billing_class = searchParams.get("billing_class") || undefined;
    const page = parseInt(searchParams.get("page") || "1");
    const pageSize = parseInt(searchParams.get("pageSize") || "50");

    const { records, total } = await getRateRecords(search, {
      billing_code,
      specialty,
      address_status,
      billing_class,
    }, page, pageSize);

    return NextResponse.json({
      records,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    });
  } catch (error) {
    console.error("Error fetching rate records:", error);
    return NextResponse.json(
      { error: "Failed to fetch rate records" },
      { status: 500 }
    );
  }
}