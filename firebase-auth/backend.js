const express = require('express');
const admin = require('firebase-admin');

// Use your exact service account credentials
const serviceAccount = {
  "type": "service_account",
  "project_id": "shejan-a82dd",
  "private_key_id": "52309d34404ad884d8c6b001bee854daf8f5d36c",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDVcJHJDQAJxut9\nln2GT9aYu4O2/kk7bj1F4k7csSFc+gYeBgqDdEPlWlInhvA0CRpA8u3FlkEm+NFx\nItin+VF0sa/5YO6bSmCU7e1Dssbmf9TtXWtrpSBS/Eb7fDkYJ6zCfBQY7slJgtkK\ndmiRDHspLUYOksfsqxRWWR6DjpmwXwICwI1N8dmeNPB8a6pZkRSAQqzGicsOaMlC\nSRca7FYhOX1AHkoik6hgarLzkoDq7oBVu8pCNXuf1+rK/d5EB8c7Ldl31QaGjGGy\nGLUXSN7RQ6Rdhf0ljjeozmwsB8ybX31qLhGr6k5daw1lpYeTPnoeGpHHiD1qkK0x\nxadX2PPzAgMBAAECggEAIpmdCHqTBwK4KiO7NYq7vwam04NlW70DMdD998i/H9No\nKnXQPn8agpOhvcaiKc1P9DdtVBqHdUngqfZ8KL7B9ajYXhTYmVP1VC89xzu0Aqm2\nWsRKJakfFFTRLPN2TfQgjWaP23raJpCPnqKTUPA1BvfP44zn2/Xf1h+cUrdLMsvo\nHkRbMSZ4+iHmmOQGSmZxuNvlwci74tlq5sI8DMG/cGiAoOj9dhmggTN20OofFi1b\nHV7boR6zFsxv0rUUm5gdeCuKCU3jgbdYnIrsM5Djll8m+30b//G/EpN+N3/YfTay\nAY9r0CZcKU7KY82XiaBB5xxSoWNLTzMxIUySxyDoAQKBgQD3g+bjCys9EX80tDoX\nHd9olMy/ka+XMYQ4Z3JYK46JPBWAEZbfshsInas71aqBIFZlVlcMcHsH7k8Wur1w\n3RupGpSRevS2g1Uc7OwKbQJMMNW5zG2fo9Q5XAS/Z/P3P7i98mno9M2N3PwIa+nW\nUeQehEwIKwF7dvCywjhL4Q6KmQKBgQDcwaJN+8vD3EFIPq9IFyVteo3dEc3r33a9\nks+9CBgb4RgDH6WG/ctbQkRIvwpP+hoAhbUaWZNpJsAv19gnmkdF1NC/AO0cvrai\nXP4w3seOmKcKT3RUUyFXpD55nAccXl6rmzOk3sVSoVOOjTQYBWf1o9+m98HTPa9k\nWgRkPgb2awKBgG8kN2Tz+vJtDOWpl/wRWeQoDNhonqQRhAGf0eRtio9s/2qGe2zv\nGNyBkAZKJ0ncL29JmcToLRael7zpFW+8mVMRsGyy/XeG+Y0HheYYlNOJii7n8MGi\nWwV2oFsiXpZDcr04QP5uDm8JL9LIQjQOiZR6a3mvdfburZ5XP9gyssjhAoGAdXGG\nmZpl03NwP7Epq161CMN0ibIZLW2bTEu4vUZ7HQnprm+9rk2DTK+6iEEqiVXzU2fO\n64/QPtbg1BMu6hLH7DzGOXeSrgJAQ6zZhsJexFwuMewHZX08ddXpbuU1W0BReVZ+\naS4jKEyvmV1B462smyBtsfSJZ4qfrvG8+F+PcLUCgYEAvoNOfzuodUDTM24QZbK2\nSp2KXyuFBNMyirgFhICtagw2ZLo0eRmDzmHOPjqjJQDMmIEm6w3ddwgslkXKnlAZ\n1hXvSc8K6lLrlVuX3dGl2jODpFZ/FiuUZ1em8nZYPvqnSZij3bus8rFcn8M+gk7Z\nhIYd9W0MqFfPGR4QeXQ2EwA=\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-zh6eg@shejan-a82dd.iam.gserviceaccount.com",
  "client_id": "111031575116293414445",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-zh6eg%40shejan-a82dd.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
};

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const app = express();
app.use(express.json());

// CORS - allow your frontend
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
  if (req.method === 'OPTIONS') {
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
    return res.status(200).json({});
  }
  next();
});

app.post('/verify', async (req, res) => {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({
      status: 401,
      success: false,
      message: 'Missing or malformed Authorization header. Expected: Bearer <token>',
      data: null
    });
  }

  const idToken = authHeader.split('Bearer ')[1];

  try {
    // This is the ONLY correct way to verify a Firebase ID Token
    const decodedToken = await admin.auth().verifyIdToken(idToken);

    return res.status(200).json({
      status: 200,
      success: true,
      message: 'Token is valid',
      data: {
        uid: decodedToken.uid,
        email: decodedToken.email,
        name: decodedToken.name
      }
    });
  } catch (error) {
    console.error('Token verification failed:', error.message);
    return res.status(401).json({
      status: 401,
      success: false,
      message: 'Invalid Firebase Token',
      data: null
    });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
  console.log('Send POST to /verify with header: Authorization: Bearer <firebase_id_token>');
});
