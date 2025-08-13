import React from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './pages/App'
import Calibration from './pages/Calibration'
import ProblemExam from './pages/ProblemExam'
import Report from './pages/Report'
import Admin from './pages/Admin'
import Home from './pages/Home'
import './styles.css'
const router=createBrowserRouter([{path:'/',element:<App/>,children:[{index:true,element:<Home/>},{path:'calibration',element:<Calibration/>},{path:'problem',element:<ProblemExam/>},{path:'report/:sid',element:<Report/>},{path:'admin',element:<Admin/>}]}])
createRoot(document.getElementById('root')!).render(<RouterProvider router={router}/>)
