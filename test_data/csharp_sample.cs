// This is a file-level comment.
using System;

namespace TestApp
{
    /// <summary>
    /// This is an XML doc comment for the class.
    /// </summary>
    public class MyTestClass
    {
        // This is a single-line comment for a method.
        public void MyMethod1()
        {
            Console.WriteLine("Hello from MyMethod1");
        }

        /*
            This is a multi-line comment.
            It spans multiple lines.
        */
        public int MyMethod2(int x, int y)
        {
            return x + y;
        }
    }
}
