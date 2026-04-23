import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Package, Users, TrendingDown, ArrowRight } from "lucide-react";

export function HomePage() {
  return (
    <div className="space-y-16">
      {/* Hero Section */}
      <section className="relative -mx-4 sm:-mx-6 md:-mx-8 px-4 sm:px-6 md:px-8 py-16 md:py-24 overflow-hidden">
        {/* Gradient Background */}
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-50 via-teal-50 to-cyan-50" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-emerald-100/40 via-transparent to-transparent" />

        {/* Decorative Elements */}
        <div className="absolute top-0 left-0 w-72 h-72 bg-emerald-200/30 rounded-full blur-3xl -translate-x-1/2 -translate-y-1/2" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-teal-200/30 rounded-full blur-3xl translate-x-1/3 translate-y-1/3" />

        <div className="relative text-center space-y-6 max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-white/80 backdrop-blur-sm rounded-full border border-emerald-200 text-sm text-emerald-700 font-medium shadow-sm">
            <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            Trusted by 500+ UK businesses
          </div>

          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl bg-gradient-to-r from-emerald-800 via-emerald-700 to-teal-700 bg-clip-text text-transparent">
            B2B Food & Beverage Marketplace
          </h1>

          <p className="text-lg md:text-xl text-emerald-900/70 max-w-2xl mx-auto leading-relaxed">
            Connect with UK suppliers and unlock{" "}
            <span className="font-semibold text-emerald-700">
              15%+ discounts
            </span>{" "}
            through group buying
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
            <Link to="/products">
              <Button
                size="lg"
                className="text-base w-full sm:w-auto shadow-lg shadow-emerald-500/25 hover:shadow-xl hover:shadow-emerald-500/30 transition-all"
              >
                Browse Products
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Link to="/buying-groups">
              <Button
                size="lg"
                variant="outline"
                className="text-base w-full sm:w-auto bg-white/80 backdrop-blur-sm hover:bg-white"
              >
                View Group Deals
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="space-y-8">
        <div className="text-center space-y-2">
          <h2 className="text-2xl md:text-3xl font-bold text-foreground">
            Why Choose Provisions Link?
          </h2>
          <p className="text-muted-foreground">
            Everything you need to source quality ingredients at better prices
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          <Card className="group relative overflow-hidden border-2 border-transparent hover:border-emerald-200 transition-all duration-300 hover:shadow-lg hover:shadow-emerald-100">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <CardHeader className="relative">
              <div className="h-12 w-12 mb-3 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/25">
                <Package className="h-6 w-6 text-white" />
              </div>
              <CardTitle className="text-xl">Quality Suppliers</CardTitle>
              <CardDescription className="text-base">
                FSA-verified vendors with hygiene ratings
              </CardDescription>
            </CardHeader>
            <CardContent className="relative text-muted-foreground">
              Browse products from certified UK food suppliers with transparent
              safety ratings.
            </CardContent>
          </Card>

          <Card className="group relative overflow-hidden border-2 border-transparent hover:border-emerald-200 transition-all duration-300 hover:shadow-lg hover:shadow-emerald-100">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <CardHeader className="relative">
              <div className="h-12 w-12 mb-3 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/25">
                <Users className="h-6 w-6 text-white" />
              </div>
              <CardTitle className="text-xl">Group Buying</CardTitle>
              <CardDescription className="text-base">
                Join forces with nearby businesses
              </CardDescription>
            </CardHeader>
            <CardContent className="relative text-muted-foreground">
              Unlock wholesale discounts by combining orders with other
              restaurants and cafes in your area.
            </CardContent>
          </Card>

          <Card className="group relative overflow-hidden border-2 border-transparent hover:border-emerald-200 transition-all duration-300 hover:shadow-lg hover:shadow-emerald-100">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <CardHeader className="relative">
              <div className="h-12 w-12 mb-3 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/25">
                <TrendingDown className="h-6 w-6 text-white" />
              </div>
              <CardTitle className="text-xl">Save Money</CardTitle>
              <CardDescription className="text-base">
                15%+ discounts available through group deals
              </CardDescription>
            </CardHeader>
            <CardContent className="relative text-muted-foreground">
              Real-time progress tracking shows you how close groups are to
              unlocking discounts.
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
