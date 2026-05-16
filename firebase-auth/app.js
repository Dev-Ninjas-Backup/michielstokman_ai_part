import { initializeApp } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/11.6.1/firebase-auth.js";

// Firebase configuration - Get your Web API Key from Firebase Console
// Go to: https://console.firebase.google.com/ > Project Settings > General > Web API Key
const firebaseConfig = {
  apiKey: "AIzaSyDtyzNoySKvKI6VyIjHT8__Acb19iMNyEE",
  authDomain: "shejan-a82dd.firebaseapp.com",
  projectId: "shejan-a82dd"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

// DOM elements
const signInBtn = document.getElementById("signInBtn");
const signOutBtn = document.getElementById("signOutBtn");
const authSection = document.getElementById("authSection");
const userInfo = document.getElementById("userInfo");
const userPhoto = document.getElementById("userPhoto");
const userName = document.getElementById("userName");
const userEmail = document.getElementById("userEmail");
const tokenSection = document.getElementById("tokenSection");
const tokenBox = document.getElementById("tokenBox");
const copyBtn = document.getElementById("copyBtn");
const errorMsg = document.getElementById("errorMsg");

function showError(msg) {
  errorMsg.textContent = msg;
  setTimeout(() => { errorMsg.textContent = ""; }, 5000);
}

// Sign in with Google
signInBtn.addEventListener("click", async () => {
  try {
    provider.setCustomParameters({ prompt: "select_account" });
    const result = await signInWithPopup(auth, provider);
    const user = result.user;
    const token = await user.getIdToken();

    // Update UI
    authSection.style.display = "none";
    userInfo.style.display = "block";
    userPhoto.src = user.photoURL || "";
    userName.textContent = user.displayName || "User";
    userEmail.textContent = user.email || "";

    // Show token
    tokenSection.style.display = "block";
    tokenBox.style.display = "block";
    tokenBox.textContent = token;

    console.log("Firebase ID Token:", token);
  } catch (error) {
    console.error("Sign in error:", error);
    showError(error.message);
  }
});

// Sign out
signOutBtn.addEventListener("click", async () => {
  try {
    await signOut(auth);
    authSection.style.display = "block";
    userInfo.style.display = "none";
    tokenSection.style.display = "none";
    tokenBox.textContent = "";
  } catch (error) {
    console.error("Sign out error:", error);
    showError(error.message);
  }
});

// Copy token
copyBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(tokenBox.textContent).then(() => {
    copyBtn.textContent = "Copied!";
    setTimeout(() => { copyBtn.textContent = "Copy Token"; }, 2000);
  });
});

// Listen for auth state changes
onAuthStateChanged(auth, async (user) => {
  if (user) {
    authSection.style.display = "none";
    userInfo.style.display = "block";
    userPhoto.src = user.photoURL || "";
    userName.textContent = user.displayName || "User";
    userEmail.textContent = user.email || "";

    const token = await user.getIdToken();
    tokenSection.style.display = "block";
    tokenBox.style.display = "block";
    tokenBox.textContent = token;
  } else {
    authSection.style.display = "block";
    userInfo.style.display = "none";
    tokenSection.style.display = "none";
  }
});
