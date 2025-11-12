import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Package, Users, TrendingDown } from 'lucide-react';

export function HomePage() {
  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <section className="text-center space-y-4 py-12">
        <h1 className="text-4xl font-bold tracking-tight sm:text-6xl md:text-6xl">
          B2B Food & Beverage Marketplace
        </h1>
        <p className="text-xl md:text-xl text-muted-foreground max-w-2xl mx-auto">
          Connect with UK suppliers and unlock 15%+ discounts through group buying
        </p>
        <div className="flex gap-4 justify-center pt-4">
          <Link to="/products">
            <Button size="lg" className="text-base md:text-base">Browse Products</Button>
          </Link>
          <Link to="/buying-groups">
            <Button size="lg" variant="outline" className="text-base md:text-base">View Group Deals</Button>
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="grid md:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <Package className="h-10 w-10 mb-2 text-primary" />
            <CardTitle>Quality Suppliers</CardTitle>
            <CardDescription>
              FSA-verified vendors with hygiene ratings
            </CardDescription>
          </CardHeader>
          <CardContent>
            Browse products from certified UK food suppliers with transparent safety ratings.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <Users className="h-10 w-10 mb-2 text-primary" />
            <CardTitle>Group Buying</CardTitle>
            <CardDescription>
              Join forces with nearby businesses
            </CardDescription>
          </CardHeader>
          <CardContent>
            Unlock wholesale discounts by combining orders with other restaurants and cafes in your area.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <TrendingDown className="h-10 w-10 mb-2 text-primary" />
            <CardTitle>Save Money</CardTitle>
            <CardDescription>
              15%+ discounts available through group deals
            </CardDescription>
          </CardHeader>
          <CardContent>
            Real-time progress tracking shows you how close groups are to unlocking discounts.
          </CardContent>
        </Card>
      </section>
    </div>
  );
}