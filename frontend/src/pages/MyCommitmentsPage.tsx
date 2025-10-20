// frontend/src/pages/MyCommitmentsPage.tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { buyingGroupsApi } from '@/api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Users, CheckCircle, XCircle, Clock, Loader2, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useToast } from '@/hooks/use-toast';

export default function MyCommitmentsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['my-commitments'],
    queryFn: () => buyingGroupsApi.myCommitments(),
  });

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Skeleton className="h-12 w-64 mb-6" />
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  const commitments = data?.data;

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">My Commitments</h1>
        <p className="text-muted-foreground">
          View and manage your buying group commitments
        </p>
      </div>

      {commitments && commitments.total_count === 0 ? (
        <Alert>
          <AlertDescription>
            You haven't joined any buying groups yet.{' '}
            <Link to="/buying-groups" className="underline">
              Browse available groups
            </Link>
          </AlertDescription>
        </Alert>
      ) : (
        <Tabs defaultValue="active" className="space-y-6">
          <TabsList>
            <TabsTrigger value="active" className="gap-2">
              <Clock className="h-4 w-4" />
              Active ({commitments?.active.length || 0})
            </TabsTrigger>
            <TabsTrigger value="confirmed" className="gap-2">
              <CheckCircle className="h-4 w-4" />
              Confirmed ({commitments?.confirmed.length || 0})
            </TabsTrigger>
            <TabsTrigger value="cancelled" className="gap-2">
              <XCircle className="h-4 w-4" />
              Cancelled ({commitments?.cancelled.length || 0})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="active" className="space-y-4">
            {commitments?.active.map((commitment) => (
              <CommitmentCard key={commitment.id} commitment={commitment} />
            ))}
          </TabsContent>

          <TabsContent value="confirmed" className="space-y-4">
            {commitments?.confirmed.map((commitment) => (
              <CommitmentCard key={commitment.id} commitment={commitment} />
            ))}
          </TabsContent>

          <TabsContent value="cancelled" className="space-y-4">
            {commitments?.cancelled.map((commitment) => (
              <CommitmentCard key={commitment.id} commitment={commitment} />
            ))}
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}

function CommitmentCard({ commitment }: { commitment: any }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const statusConfig = {
    pending: { icon: Clock, color: 'text-yellow-600', bg: 'bg-yellow-100' },
    confirmed: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-100' },
    cancelled: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-100' },
  };

  const status = statusConfig[commitment.status as keyof typeof statusConfig];
  const StatusIcon = status.icon;

  // FIX 7: Cancel mutation with comprehensive cache invalidation
  const cancelMutation = useMutation({
    mutationFn: () => buyingGroupsApi.cancelCommitment(commitment.group),
    onSuccess: () => {
      // Invalidate the commitments list (this page)
      queryClient.invalidateQueries({ queryKey: ['my-commitments'] });
      
      // ADDED: Invalidate the buying groups list page
      queryClient.invalidateQueries({ queryKey: ['buying-groups'] });
      
      // ADDED: Invalidate the specific group detail page
      queryClient.invalidateQueries({ queryKey: ['buying-group', commitment.group] });
      
      toast({
        title: 'Commitment Cancelled',
        description: 'Your commitment has been cancelled and payment hold released.',
      });
    },
    onError: (error: any) => {
      toast({
        title: 'Cancellation Failed',
        description: error.response?.data?.error || 'Failed to cancel commitment',
        variant: 'destructive',
      });
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="text-lg mb-2">
              <Link 
                to={`/buying-groups/${commitment.group}`}
                className="hover:text-primary flex items-center gap-2"
              >
                Group #{commitment.group}
                <ExternalLink className="h-4 w-4" />
              </Link>
            </CardTitle>
            <div className="flex items-center gap-2">
              <StatusIcon className={`h-4 w-4 ${status.color}`} />
              <Badge className={status.bg}>
                {commitment.status.toUpperCase()}
              </Badge>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Quantity</p>
            <p className="font-medium">{commitment.quantity} units</p>
          </div>
          <div>
            <p className="text-muted-foreground">Total Price</p>
            <p className="font-medium">£{parseFloat(commitment.total_price).toFixed(2)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Savings</p>
            <p className="font-medium text-green-600">
              £{parseFloat(commitment.total_savings).toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Committed</p>
            <p className="font-medium">
              {new Date(commitment.committed_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        {/* Actions based on status */}
        <div className="flex gap-2 pt-2">
          {/* Cancel button for pending commitments */}
          {commitment.status === 'pending' && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button 
                  variant="destructive" 
                  size="sm"
                  className="flex-1"
                  disabled={cancelMutation.isPending}
                >
                  {cancelMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Cancelling...
                    </>
                  ) : (
                    'Cancel Commitment'
                  )}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Cancel Commitment?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Are you sure you want to cancel your commitment of {commitment.quantity} units?
                    Your payment hold will be released.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep Commitment</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => cancelMutation.mutate()}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Cancel Commitment
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}

          {/* View Order button for confirmed commitments */}
          {commitment.status === 'confirmed' && commitment.order && (
            <Button asChild variant="default" size="sm" className="flex-1">
              <Link to={`/orders/${commitment.order}`}>
                <ExternalLink className="h-4 w-4 mr-2" />
                View Order
              </Link>
            </Button>
          )}

          {/* View Group button (always available) */}
          <Button asChild variant="outline" size="sm" className="flex-1">
            <Link to={`/buying-groups/${commitment.group}`}>
              View Group
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}