import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Spinner } from "./spinner";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium tracking-tight transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-cyan/70 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:pointer-events-none disabled:opacity-45 active:translate-y-px select-none",
  {
    variants: {
      variant: {
        primary:
          "text-white gradient-bg shadow-[0_8px_24px_-12px_rgba(99,102,241,0.9)] hover:brightness-110 hover:shadow-[0_12px_28px_-12px_rgba(99,102,241,1)]",
        secondary:
          "bg-surface-raised text-ink border border-line hover:border-line-strong hover:bg-surface-hover",
        soft: "bg-accent-soft text-accent border border-accent/25 hover:border-accent/45",
        ghost: "text-ink-muted hover:text-ink hover:bg-surface-hover",
        outline: "border border-line-strong text-ink hover:bg-surface-hover",
        danger:
          "bg-rose/12 text-rose border border-rose/30 hover:bg-rose/20 hover:border-rose/45",
        link: "text-accent underline-offset-4 hover:underline",
      },
      size: {
        xs: "h-7 px-2.5 text-xs rounded-md",
        sm: "h-8 px-3 text-[13px]",
        md: "h-9 px-4 text-sm",
        lg: "h-11 px-5 text-sm",
        icon: "h-9 w-9",
        "icon-sm": "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <>
            <Spinner className="h-3.5 w-3.5" />
            {children}
          </>
        ) : (
          children
        )}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
