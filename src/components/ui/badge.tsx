import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider transition-colors',
  {
    variants: {
      variant: {
        default:     'bg-primary/10 text-primary',
        secondary:   'bg-secondary text-muted-foreground border border-border',
        critical:    'bg-destructive/10 text-destructive',
        attention:   'bg-amber-500/10 text-amber-600',
        info:        'bg-primary/10 text-primary',
        active:      'bg-emerald-500/10 text-emerald-600',
        resolved:    'bg-muted/60 text-muted-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
