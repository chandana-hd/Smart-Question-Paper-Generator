import React, { useState, useEffect, createContext, useContext } from 'react';
import { initializeApp } from 'firebase/app';
import {
  getAuth,
  signInWithCustomToken,
  onAuthStateChanged,
  signOut as firebaseSignOut,
  signInAnonymously,
  createUserWithEmailAndPassword, // Added for registration
  signInWithEmailAndPassword,     // Added for login
  deleteUser
} from 'firebase/auth';
import { getFirestore, doc, setDoc, collection, query, onSnapshot, orderBy, deleteDoc } from 'firebase/firestore';
import { Menu, X, Settings, HelpCircle, Sun, Moon, LogOut, User, Folder, Clock, Share2, Download, Trash2, Edit3, PlusCircle, Eye } from 'lucide-react'; // Importing icons

// --- Firebase Context ---
const FirebaseContext = createContext(null);

const FirebaseProvider = ({ children }) => {
  const [app, setApp] = useState(null);
  const [db, setDb] = useState(null);
  const [auth, setAuth] = useState(null);
  const [userId, setUserId] = useState(null);
  const [isAuthReady, setIsAuthReady] = useState(false);

  useEffect(() => {
    try {
      // Access environment variables for local development
      // For Canvas environment, __firebase_config, __initial_auth_token, __app_id are global.
      // For local development, we use process.env.REACT_APP_... variables.
      const firebaseConfig = process.env.REACT_APP_FIREBASE_CONFIG
        ? JSON.parse(process.env.REACT_APP_FIREBASE_CONFIG)
        : (typeof __firebase_config !== 'undefined' ? JSON.parse(__firebase_config) : null);

      const initialAuthToken = process.env.REACT_APP_INITIAL_AUTH_TOKEN
        ? process.env.REACT_APP_INITIAL_AUTH_TOKEN
        : (typeof __initial_auth_token !== 'undefined' ? __initial_auth_token : null);

      const appId = process.env.REACT_APP_APP_ID
        ? process.env.REACT_APP_APP_ID
        : (typeof __app_id !== 'undefined' ? __app_id : 'default-app-id');


      if (!firebaseConfig) {
        console.error("Firebase config not found. Please ensure REACT_APP_FIREBASE_CONFIG is set in your .env file or __firebase_config is set in Canvas.");
        return;
      }

      const firebaseApp = initializeApp(firebaseConfig);
      const firestoreDb = getFirestore(firebaseApp);
      const firebaseAuth = getAuth(firebaseApp);

      setApp(firebaseApp);
      setDb(firestoreDb);
      setAuth(firebaseAuth);

      const unsubscribe = onAuthStateChanged(firebaseAuth, async (user) => {
        if (user) {
          setUserId(user.uid);
          console.log("User signed in:", user.uid);
        } else {
          console.log("No user signed in. Attempting anonymous sign-in or custom token sign-in.");
          if (initialAuthToken) {
            try {
              await signInWithCustomToken(firebaseAuth, initialAuthToken);
              console.log("Signed in with custom token.");
            } catch (error) {
              console.error("Error signing in with custom token:", error);
              // Fallback to anonymous if custom token fails
              try {
                await signInAnonymously(firebaseAuth);
                console.log("Signed in anonymously after custom token failure.");
              } catch (anonError) {
                console.error("Error signing in anonymously:", anonError);
              }
            }
          } else {
            try {
              await signInAnonymously(firebaseAuth);
                console.log("Signed in anonymously.");
            } catch (error) {
              console.error("Error signing in anonymously:", error);
            }
          }
          setUserId(firebaseAuth.currentUser?.uid || crypto.randomUUID()); // Ensure userId is set even for anonymous
        }
        setIsAuthReady(true);
      });

      return () => unsubscribe(); // Cleanup auth listener
    } catch (error) {
      console.error("Error initializing Firebase:", error);
    }
  }, []);

  return (
    <FirebaseContext.Provider value={{ app, db, auth, userId, isAuthReady }}>
      {children}
    </FirebaseContext.Provider>
  );
};

// --- Theme Context ---
const ThemeContext = createContext(null);

const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(() => {
    // Initialize theme from localStorage or default to 'light'
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') || 'light';
    }
    return 'light';
  });

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const root = window.document.documentElement;
      root.classList.remove('light', 'dark');
      root.classList.add(theme);
      localStorage.setItem('theme', theme);
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prevTheme) => (prevTheme === 'light' ? 'dark' : 'light'));
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

// --- Components ---

// Message Box Component (replaces alert/confirm)
const MessageBox = ({ message, onConfirm, onCancel, showCancel = false }) => {
  if (!message) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-sm w-full text-center">
        <p className="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">{message}</p>
        <div className="flex justify-center space-x-4">
          {showCancel && (
            <button
              onClick={onCancel}
              className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              Cancel
            </button>
          )}
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
};

const Auth = ({ setAuthStatus, setMessageBox }) => {
  const { auth, isAuthReady } = useContext(FirebaseContext);
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [username, setUsername] = useState(''); // For registration

  const handleAuth = async (e) => {
    e.preventDefault();
    setMessage('');
    if (!auth || !isAuthReady) {
      setMessage("Firebase not ready. Please wait.");
      return;
    }

    try {
      if (isLogin) {
        // Firebase client-side login
        const userCredential = await signInWithEmailAndPassword(auth, email, password);
        const user = userCredential.user;
        const idToken = await user.getIdToken(); // Get Firebase ID token

        // Send ID token to backend for verification/session management (optional but good practice)
        // For now, we'll just log it and proceed.
        console.log("Firebase ID Token:", idToken);

        setMessageBox({ message: "Login successful! Redirecting...", onConfirm: () => setMessageBox(null) });
        setAuthStatus(true);
      } else {
        // Firebase client-side registration
        const userCredential = await createUserWithEmailAndPassword(auth, email, password);
        const user = userCredential.user;
        // You might want to update user profile with username here if needed
        // await updateProfile(user, { displayName: username });

        setMessageBox({ message: "Registration successful! Please login.", onConfirm: () => { setMessageBox(null); setIsLogin(true); } });
      }
    } catch (error) {
      console.error("Authentication error:", error);
      setMessage(`Error: ${error.message}`);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 font-inter">
      <div className="bg-white dark:bg-gray-800 p-8 rounded-lg shadow-lg w-full max-w-md">
        <h2 className="text-2xl font-bold text-center mb-6 text-gray-900 dark:text-gray-100">
          {isLogin ? 'Login' : 'Register'} to SmartQPGen
        </h2>
        <form onSubmit={handleAuth}>
          {!isLogin && (
            <div className="mb-4">
              <label className="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2" htmlFor="username">
                Username
              </label>
              <input
                type="text"
                id="username"
                className="shadow appearance-none border rounded-md w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required={!isLogin}
              />
            </div>
          )}
          <div className="mb-4">
            <label className="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2" htmlFor="email">
              Email
            </label>
            <input
              type="email"
              id="email"
              className="shadow appearance-none border rounded-md w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="mb-6">
            <label className="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2" htmlFor="password">
              Password
            </label>
            <input
              type="password"
              id="password"
              className="shadow appearance-none border rounded-md w-full py-2 px-3 text-gray-700 mb-3 leading-tight focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {message && <p className="text-red-500 text-sm mb-4 text-center">{message}</p>}
          <div className="flex items-center justify-between">
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors w-full"
            >
              {isLogin ? 'Sign In' : 'Register'}
            </button>
          </div>
        </form>
        <p className="text-center text-gray-600 dark:text-gray-400 text-sm mt-4">
          {isLogin ? "Don't have an account?" : "Already have an account?"}{' '}
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="text-blue-600 hover:text-blue-700 font-bold focus:outline-none"
          >
            {isLogin ? 'Register' : 'Login'}
          </button>
        </p>
      </div>
    </div>
  );
};

const Sidebar = ({ isOpen, toggleSidebar, setView, userId, setMessageBox }) => {
  const { auth } = useContext(FirebaseContext);

  const handleSignOut = async () => {
    setMessageBox({
      message: "Are you sure you want to sign out?",
      showCancel: true,
      onConfirm: async () => {
        try {
          if (auth) {
            await firebaseSignOut(auth);
            console.log("User signed out.");
            window.location.reload(); // Simple reload to go back to login
          }
        } catch (error) {
          console.error("Error signing out:", error);
          setMessageBox({ message: `Sign out error: ${error.message}`, onConfirm: () => setMessageBox(null) });
        } finally {
          setMessageBox(null);
        }
      },
      onCancel: () => setMessageBox(null)
    });
  };

  const SidebarItem = ({ icon: Icon, text, onClick, active }) => (
    <button
      onClick={onClick}
      className={`flex items-center w-full px-4 py-2 rounded-md text-left transition-colors duration-200
        ${active ? 'bg-blue-600 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}
        focus:outline-none focus:ring-2 focus:ring-blue-500`}
    >
      <Icon size={20} className="mr-3" />
      <span className="font-medium">{text}</span>
    </button>
  );

  return (
    <div
      className={`fixed inset-y-0 left-0 bg-gray-50 dark:bg-gray-800 w-64 p-4 flex flex-col transition-transform duration-300 ease-in-out z-40
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        lg:translate-x-0 lg:static lg:shadow-none lg:border-r lg:border-gray-200 dark:lg:border-gray-700`}
    >
      <div className="flex items-center justify-between mb-6 lg:hidden">
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">SmartQPGen</h1>
        <button onClick={toggleSidebar} className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 focus:outline-none">
          <X size={24} />
        </button>
      </div>

      <div className="flex flex-col space-y-2 flex-grow">
        <SidebarItem icon={PlusCircle} text="New Question Paper" onClick={() => setView('new-qp')} active={false} />
        <SidebarItem icon={Folder} text="Saved QBs & Templates" onClick={() => setView('saved-qbs')} active={false} />
        <SidebarItem icon={Clock} text="Recent Generated Papers" onClick={() => setView('recent-papers')} active={false} />
      </div>

      <div className="mt-auto space-y-2 border-t pt-4 border-gray-200 dark:border-gray-700">
        <SidebarItem icon={Settings} text="Settings" onClick={() => setView('settings')} active={false} />
        <SidebarItem icon={LogOut} text="Sign Out" onClick={handleSignOut} active={false} />
      </div>
      {userId && (
        <div className="mt-4 text-sm text-gray-500 dark:text-gray-400">
          User ID: <span className="break-all">{userId}</span>
        </div>
      )}
    </div>
  );
};

const AccountMenu = ({ setMessageBox, setAuthStatus }) => {
  const { auth, userId } = useContext(FirebaseContext);
  const [isOpen, setIsOpen] = useState(false);

  const handleSignOut = async () => {
    setMessageBox({
      message: "Are you sure you want to sign out?",
      showCancel: true,
      onConfirm: async () => {
        try {
          if (auth) {
            await firebaseSignOut(auth);
            console.log("User signed out.");
            setAuthStatus(false); // Update auth status in App.js
          }
        } catch (error) {
          console.error("Error signing out:", error);
          setMessageBox({ message: `Sign out error: ${error.message}`, onConfirm: () => setMessageBox(null) });
        } finally {
          setMessageBox(null);
        }
      },
      onCancel: () => setMessageBox(null)
    });
  };

  const handleDeleteAccount = () => {
    setMessageBox({
      message: "This will permanently delete your account. Are you sure?",
      showCancel: true,
      onConfirm: async () => {
        try {
          if (auth && auth.currentUser) {
            // Firebase requires re-authentication for security-sensitive operations like deleteUser.
            // For a real app, you'd prompt the user to re-enter their password here.
            // For this example, we'll just simulate success or show an error if not re-authenticated.
            await deleteUser(auth.currentUser);
            console.log("Account deleted.");
            setAuthStatus(false);
          } else {
            setMessageBox({ message: "No user logged in to delete or re-authentication required.", onConfirm: () => setMessageBox(null) });
          }
        } catch (error) {
          console.error("Error deleting account:", error);
          setMessageBox({ message: `Account deletion error: ${error.message}. Please re-authenticate and try again.`, onConfirm: () => setMessageBox(null) });
        } finally {
          setMessageBox(null);
        }
      },
      onCancel: () => setMessageBox(null)
    });
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 focus:outline-none"
      >
        <User size={24} />
        <span className="hidden md:block font-medium">{auth?.currentUser?.email || 'Guest User'}</span>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-md shadow-lg py-1 z-50">
          <div className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
            <p className="font-semibold">{auth?.currentUser?.email || 'Guest User'}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 break-all">{userId}</p>
          </div>
          <button
            onClick={() => { /* Add Account Logic */ setIsOpen(false); setMessageBox({message: "Add Account functionality is not yet implemented.", onConfirm: () => setMessageBox(null)}); }}
            className="flex items-center w-full px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <PlusCircle size={16} className="mr-2" /> Add Account
          </button>
          <button
            onClick={() => { /* Sign In/Switch Account Logic */ setIsOpen(false); setMessageBox({message: "Sign In/Switch Account functionality is not yet implemented.", onConfirm: () => setMessageBox(null)}); }}
            className="flex items-center w-full px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <User size={16} className="mr-2" /> Sign In / Switch
          </button>
          <button
            onClick={() => { handleDeleteAccount(); setIsOpen(false); }}
            className="flex items-center w-full px-4 py-2 text-sm text-red-600 hover:bg-red-100 dark:hover:bg-red-900"
          >
            <Trash2 size={16} className="mr-2" /> Delete Account
          </button>
          <button
            onClick={() => { handleSignOut(); setIsOpen(false); }}
            className="flex items-center w-full px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 border-t border-gray-200 dark:border-gray-700 mt-1 pt-2"
          >
            <LogOut size={16} className="mr-2" /> Sign Out
          </button>
        </div>
      )}
    </div>
  );
};

const MainCanvas = ({ currentView, setMessageBox }) => {
  const { db, userId, isAuthReady } = useContext(FirebaseContext);
  const { toggleTheme, theme } = useContext(ThemeContext); // Access theme context
  const [recentPapers, setRecentPapers] = useState([]);
  const [savedQBs, setSavedQBs] = useState([]);
  const [message, setMessage] = useState('');

  // Fetch recent papers
  useEffect(() => {
    if (!db || !userId || !isAuthReady) return;

    const q = query(
      collection(db, `artifacts/${process.env.REACT_APP_APP_ID || (typeof __app_id !== 'undefined' ? __app_id : 'default-app-id')}/users/${userId}/generated_papers`),
      orderBy('timestamp', 'desc')
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const papers = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      setRecentPapers(papers);
      console.log("Fetched recent papers:", papers);
    }, (error) => {
      console.error("Error fetching recent papers:", error);
      setMessage(`Error fetching papers: ${error.message}`);
    });

    return () => unsubscribe();
  }, [db, userId, isAuthReady]);

  // Fetch saved question banks (dummy for now)
  useEffect(() => {
    if (!db || !userId || !isAuthReady) return;
    // Dummy data for saved QBs & Templates
    setSavedQBs([
      { id: 'qb1', name: 'Module 1 - Data Structures QB', type: 'Question Bank', date: '2025-07-01' },
      { id: 'tmpl1', name: 'VTU Exam Template - 2024 Scheme', type: 'Template', date: '2024-11-15' },
    ]);
  }, [db, userId, isAuthReady]);


  const handleAction = (action, paperId, paperName) => {
    setMessageBox({
      message: `Performing ${action} for "${paperName}" (ID: ${paperId}). This is a placeholder.`,
      onConfirm: () => setMessageBox(null)
    });
  };

  const handleDeletePaper = (paperId, paperName) => {
    setMessageBox({
      message: `Are you sure you want to delete "${paperName}"?`,
      showCancel: true,
      onConfirm: async () => {
        try {
          if (db && userId) {
            await deleteDoc(doc(db, `artifacts/${process.env.REACT_APP_APP_ID || (typeof __app_id !== 'undefined' ? __app_id : 'default-app-id')}/users/${userId}/generated_papers`, paperId));
            setMessageBox({ message: `"${paperName}" deleted successfully.`, onConfirm: () => setMessageBox(null) });
          } else {
            setMessageBox({ message: "Database not ready or user not authenticated.", onConfirm: () => setMessageBox(null) });
          }
        } catch (error) {
          console.error("Error deleting paper:", error);
          setMessageBox({ message: `Error deleting paper: ${error.message}`, onConfirm: () => setMessageBox(null) });
        } finally {
          setMessageBox(null);
        }
      },
      onCancel: () => setMessageBox(null)
    });
  };


  const renderContent = () => {
    switch (currentView) {
      case 'new-qp':
        return (
          <div className="p-6">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Generate New Question Paper</h2>
            <p className="text-gray-700 dark:text-gray-300">
              This is where you'll define the requirements for your new question paper.
              (e.g., Subject, Module(s), Number of questions, Bloom's levels, Marks, Duration).
              We'll build this form in a later iteration!
            </p>
            {/* Dummy form for now */}
            <div className="mt-6 p-4 bg-gray-100 dark:bg-gray-700 rounded-lg">
              <label htmlFor="subject" className="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">Subject</label>
              <input type="text" id="subject" placeholder="e.g., Data Structures & Algorithms" className="shadow appearance-none border rounded-md w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-600 dark:text-gray-200 dark:border-gray-500" />
              <button
                onClick={() => setMessageBox({ message: "This will trigger the question paper generation process!", onConfirm: () => setMessageBox(null) })}
                className="mt-4 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
              >
                Generate Paper
              </button>
              <button
                onClick={async () => {
                  if (!db || !userId) {
                    setMessageBox({ message: "Database not ready or user not authenticated.", onConfirm: () => setMessageBox(null) });
                    return;
                  }
                  try {
                    const newPaperRef = doc(collection(db, `artifacts/${process.env.REACT_APP_APP_ID || (typeof __app_id !== 'undefined' ? __app_id : 'default-app-id')}/users/${userId}/generated_papers`));
                    await setDoc(newPaperRef, {
                      name: `Sample Paper ${new Date().toLocaleTimeString()}`,
                      timestamp: new Date().toISOString(),
                      status: 'Generated',
                      module: 'Module 1',
                      marks: 100,
                      questions: [
                        { q: "Explain data structures.", marks: 10, blooms: "L2" },
                        { q: "Implement bubble sort.", marks: 15, blooms: "L3" }
                      ]
                    });
                    setMessageBox({ message: "Sample paper saved to Recent!", onConfirm: () => setMessageBox(null) });
                  } catch (error) {
                    console.error("Error saving sample paper:", error);
                    setMessageBox({ message: `Error saving sample paper: ${error.message}`, onConfirm: () => setMessageBox(null) });
                  }
                }}
                className="ml-2 mt-4 px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 transition-colors"
              >
                Save Sample Paper (for testing Recent)
              </button>
            </div>
          </div>
        );
      case 'saved-qbs':
        return (
          <div className="p-6">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Saved Question Banks & Templates</h2>
            <p className="text-gray-700 dark:text-gray-300 mb-4">
              Manage your uploaded question banks and custom paper templates here.
            </p>
            {savedQBs.length === 0 ? (
              <p className="text-gray-500 dark:text-gray-400">No saved question banks or templates yet.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {savedQBs.map((item) => (
                  <div key={item.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex flex-col justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{item.name}</h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{item.type} - {item.date}</p>
                    </div>
                    <div className="flex space-x-2 mt-4">
                      <button
                        onClick={() => handleAction('View', item.id, item.name)}
                        className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                        title="View"
                      >
                        <Eye size={18} />
                      </button>
                      <button
                        onClick={() => handleAction('Edit', item.id, item.name)}
                        className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                        title="Edit"
                      >
                        <Edit3 size={18} />
                      </button>
                      <button
                        onClick={() => handleAction('Delete', item.id, item.name)}
                        className="p-2 rounded-full text-red-600 hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      case 'recent-papers':
        const N_RECENT_PAPERS = 5; // Display only the last N papers
        return (
          <div className="p-6">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Recent Generated Papers</h2>
            {message && <p className="text-red-500 text-sm mb-4">{message}</p>}
            {recentPapers.length === 0 ? (
              <p className="text-gray-500 dark:text-gray-400">No recent papers generated yet. Generate one from 'New Question Paper'!</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {recentPapers.slice(0, N_RECENT_PAPERS).map((paper) => (
                  <div key={paper.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex flex-col justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{paper.name}</h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        Generated: {new Date(paper.timestamp).toLocaleString()}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        Marks: {paper.marks || 'N/A'} | Module: {paper.module || 'N/A'}
                      </p>
                    </div>
                    <div className="flex space-x-2 mt-4">
                      <button
                        onClick={() => handleAction('View', paper.id, paper.name)}
                        className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                        title="View"
                      >
                        <Eye size={18} />
                      </button>
                      <button
                        onClick={() => handleAction('Rename', paper.id, paper.name)}
                        className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                        title="Rename"
                      >
                        <Edit3 size={18} />
                      </button>
                      <button
                        onClick={() => handleAction('Share', paper.id, paper.name)}
                        className="p-2 rounded-full text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors"
                        title="Share"
                      >
                        <Share2 size={18} />
                      </button>
                      <button
                        onClick={() => handleAction('Download DOCX', paper.id, paper.name)}
                        className="p-2 rounded-full text-green-600 hover:bg-green-100 dark:hover:bg-green-900 transition-colors"
                        title="Download DOCX"
                      >
                        <Download size={18} />
                      </button>
                      <button
                        onClick={() => handleAction('Download PDF', paper.id, paper.name)}
                        className="p-2 rounded-full text-red-600 hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
                        title="Download PDF"
                      >
                        <Download size={18} />
                      </button>
                      <button
                        onClick={() => handleDeletePaper(paper.id, paper.name)}
                        className="p-2 rounded-full text-red-600 hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      case 'settings':
        return (
          <div className="p-6">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Settings</h2>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
              <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">Theme</h3>
              <div className="flex items-center space-x-4">
                <button
                  onClick={toggleTheme}
                  className="flex items-center px-4 py-2 rounded-md bg-gray-200 text-gray-800 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {theme === 'light' ? <Moon size={20} className="mr-2" /> : <Sun size={20} className="mr-2" />}
                  Switch to {theme === 'light' ? 'Dark Mode' : 'Light Mode'}
                </button>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
              <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">Activity Log</h3>
              <p className="text-gray-700 dark:text-gray-300">
                (Placeholder) This section will show your recent login, logout, and other app activities.
              </p>
              {/* Dummy activity log */}
              <ul className="mt-4 space-y-2 text-gray-700 dark:text-gray-300">
                <li><span className="font-semibold">2025-07-20 14:00:00:</span> Logged in</li>
                <li><span className="font-semibold">2025-07-20 13:55:00:</span> Generated "Sample Paper 1"</li>
                <li><span className="font-semibold">2025-07-20 13:00:00:</span> Logged out</li>
              </ul>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
              <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">Saved Papers (All)</h3>
              <p className="text-gray-700 dark:text-gray-300 mb-4">
                This section lists all your generated question papers with full management options.
              </p>
              {recentPapers.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400">No saved papers yet.</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {recentPapers.map((paper) => (
                    <div key={paper.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex flex-col justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{paper.name}</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                          Generated: {new Date(paper.timestamp).toLocaleString()}
                        </p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                          Marks: {paper.marks || 'N/A'} | Module: {paper.module || 'N/A'}
                        </p>
                      </div>
                      <div className="flex space-x-2 mt-4">
                        <button
                          onClick={() => handleAction('View', paper.id, paper.name)}
                          className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                          title="View"
                        >
                          <Eye size={18} />
                        </button>
                        <button
                          onClick={() => handleAction('Rename', paper.id, paper.name)}
                          className="p-2 rounded-full text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                          title="Rename"
                        >
                          <Edit3 size={18} />
                        </button>
                        <button
                          onClick={() => handleAction('Share', paper.id, paper.name)}
                          className="p-2 rounded-full text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors"
                          title="Share"
                        >
                          <Share2 size={18} />
                        </button>
                        <button
                          onClick={() => handleAction('Download DOCX', paper.id, paper.name)}
                          className="p-2 rounded-full text-green-600 hover:bg-green-100 dark:hover:bg-green-900 transition-colors"
                          title="Download DOCX"
                        >
                          <Download size={18} />
                        </button>
                        <button
                          onClick={() => handleAction('Download PDF', paper.id, paper.name)}
                          className="p-2 rounded-full text-red-600 hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
                          title="Download PDF"
                        >
                          <Download size={18} />
                        </button>
                        <button
                          onClick={() => handleDeletePaper(paper.id, paper.name)}
                          className="p-2 rounded-full text-red-600 hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
                          title="Delete"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      case 'help':
        return (
          <div className="p-6">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Help & Usage Guide</h2>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
              <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">Welcome to SmartQPGen!</h3>
              <p className="text-gray-700 dark:text-gray-300 mb-4">
                This application helps faculty members at VTU-affiliated colleges to automatically generate question papers based on predefined question banks and templates.
              </p>
              <h4 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">How to Use:</h4>
              <ul className="list-disc list-inside text-gray-700 dark:text-gray-300 space-y-2">
                <li>
                  <strong>New Question Paper:</strong> Click this to start generating a new paper. You'll specify subject, modules, difficulty (Bloom's Taxonomy levels), and other criteria.
                </li>
                <li>
                  <strong>Saved QBs & Templates:</strong> Here you can upload and manage your question banks (in the specified VTU table format) and custom question paper templates.
                </li>
                <li>
                  <strong>Recent Generated Papers:</strong> Quickly access and manage your last 5 generated question papers. You can view, rename, share, download (DOCX/PDF), or delete them.
                </li>
                <li>
                  <strong>Settings:</strong> Access your activity log, view all generated papers, and change the application theme (light/dark mode).
                </li>
                <li>
                  <strong>Account:</strong> Manage your user details, sign out, or delete your account.
                </li>
              </ul>
              <p className="mt-4 text-gray-700 dark:text-gray-300">
                For detailed instructions on PDF parsing and question bank formatting, please refer to the documentation (coming soon!).
              </p>
            </div>
          </div>
        );
      default:
        return (
          <div className="p-6 text-center flex flex-col items-center justify-center h-full">
            <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">Welcome to SmartQPGen!</h2>
            <p className="text-lg text-gray-700 dark:text-gray-300 mb-6">
              Your intelligent question paper generator for VTU-affiliated colleges.
            </p>
            <button
              onClick={() => setMessageBox({ message: "This is the main canvas area. Content will appear here when you select an option from the sidebar.", onConfirm: () => setMessageBox(null) })}
              className="px-6 py-3 bg-blue-600 text-white rounded-full text-lg font-semibold hover:bg-blue-700 transition-colors shadow-lg"
            >
              Start Exploring
            </button>
          </div>
        );
    }
  };

  return (
    <div className="flex-grow p-4 overflow-auto">
      {renderContent()}
    </div>
  );
};

// Main App Component
function App() {
  const [isAuth, setIsAuth] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [currentView, setCurrentView] = useState('home'); // 'home', 'new-qp', 'saved-qbs', 'recent-papers', 'settings', 'help'
  const [messageBox, setMessageBox] = useState(null); // { message, onConfirm, onCancel, showCancel }

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
  };

  const setAuthStatus = (status) => {
    setIsAuth(status);
  };

  const { isAuthReady } = useContext(FirebaseContext);

  if (!isAuthReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-inter">
        <p>Loading application...</p>
      </div>
    );
  }

  if (!isAuth) {
    return <Auth setAuthStatus={setAuthStatus} setMessageBox={setMessageBox} />;
  }

  return (
    <div className="flex h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-inter">
      {messageBox && (
        <MessageBox
          message={messageBox.message}
          onConfirm={messageBox.onConfirm}
          onCancel={messageBox.onCancel}
          showCancel={messageBox.showCancel}
        />
      )}
      <Sidebar
        isOpen={isSidebarOpen}
        toggleSidebar={toggleSidebar}
        setView={setCurrentView}
        setMessageBox={setMessageBox}
      />

      {/* Main content area, now pushed by sidebar */}
      <div
        className={`flex flex-col flex-1 overflow-hidden transition-all duration-300 ease-in-out
          ${isSidebarOpen ? 'ml-64' : 'ml-0'}
          lg:ml-64`}
      >
        <header className="flex items-center justify-between p-4 bg-white dark:bg-gray-800 shadow-md z-30">
          <div className="flex items-center">
            <button
              onClick={toggleSidebar}
              className="lg:hidden text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 mr-4 focus:outline-none"
            >
              <Menu size={24} />
            </button>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">SmartQPGen</h1>
          </div>
          <AccountMenu setMessageBox={setMessageBox} setAuthStatus={setAuthStatus} />
        </header>

        <main className="flex-1 flex overflow-hidden">
          <MainCanvas currentView={currentView} setMessageBox={setMessageBox} />
        </main>
      </div>
    </div>
  );
}

// Wrap App with providers
export default function ProvidedApp() {
  return (
    <FirebaseProvider>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </FirebaseProvider>
  );
}
