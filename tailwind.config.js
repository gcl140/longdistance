/** @type {import('tailwindcss').Config} */
module.exports = {
  // Scan every template + every JS file in static for class names. Add new
  // paths here if you ever introduce a new app or move templates.
  content: [
    "./**/templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        netflix: {
          red: "#E50914",
          dark: "#141414",
          black: "#000000",
          gray: "#808080",
          lightgray: "#b3b3b3",
        },
        maroon: {
          50: "#fff8f8",
          100: "#feecee",
          300: "#E50914",
          500: "#E50914",
          700: "#b20710",
          900: "#831010",
          55: "#591213",
        },
      },
      fontFamily: {
        sen: ["Inter", "sans-serif"],
        playfair: ["Playfair Display", "serif"],
      },
      keyframes: {
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
      animation: { float: "float 6s ease-in-out infinite" },
    },
  },
  plugins: [],
};
