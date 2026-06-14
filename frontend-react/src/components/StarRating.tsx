import { useState } from "react";
import { Star } from "lucide-react";

interface Props {
  onRate: (score: number) => void;
  disabled?: boolean;
}

export function StarRating({ onRate, disabled }: Props) {
  const [hover, setHover] = useState(0);
  const [selected, setSelected] = useState(0);

  const handleClick = (score: number) => {
    if (disabled) return;
    setSelected(score);
    onRate(score);
  };

  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((score) => (
        <button
          key={score}
          disabled={disabled}
          onClick={() => handleClick(score)}
          onMouseEnter={() => setHover(score)}
          onMouseLeave={() => setHover(0)}
          className="p-0.5 transition-colors disabled:cursor-default"
        >
          <Star
            className={`w-5 h-5 transition-colors ${
              score <= (hover || selected)
                ? "fill-amber-400 text-amber-400"
                : "text-[var(--color-muted-foreground)]"
            }`}
          />
        </button>
      ))}
      {selected > 0 && (
        <span className="text-xs text-[var(--color-muted-foreground)] ml-2">
          {selected === 5 ? "太棒了!" : selected === 4 ? "很不错" : selected === 3 ? "一般" : selected === 2 ? "需改进" : "很差"}
        </span>
      )}
    </div>
  );
}
