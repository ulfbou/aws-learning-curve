/** @type {import("tailwindcss").Config} */
export default {
  content: [
    "./public/index.html",
    "./public/app.js"
  ],
  theme: {
    extend: {
      colors: {
        aws: "#ff9900",
        navy: "#232f3e",
        cloud: "#f5f7fb"
      },
      boxShadow: {
        panel: "0 16px 50px rgba(35, 47, 62, 0.12)"
      }
    }
  },
  plugins: []
};
