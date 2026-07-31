/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./public/**/*.html", // Scans all HTML files in the public directory and its subdirectories
    "./src/**/*.{js,html}", // Scans all JavaScript and HTML files in src and its subdirectories
    // Add any other paths here if you plan to use Tailwind classes in other file types
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}