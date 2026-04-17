import { type HTMLAttributes } from "react";
import clsx from "clsx";
import "./Card.css";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  elevated?: boolean;
  subtle?: boolean;
}

export function Card({ elevated, subtle, className, children, ...rest }: CardProps) {
  return (
    <div
      className={clsx("card", elevated && "card-elevated", subtle && "card-subtle", className)}
      {...rest}
    >
      {children}
    </div>
  );
}
