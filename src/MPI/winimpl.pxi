cdef void win_memory_pydecref(void *ob) with gil:
    Py_DECREF(<PyObject*>ob)

#@cython.callspec("PyMPI_API_CALL")
cdef int PyMPI_Win_memory_del(MPI_Win w, int k, void *v, void *xs) nogil:
    if  v != NULL:
        if Py_IsInitialized():
            win_memory_pydecref(v)
    return MPI_SUCCESS

cdef int PyMPI_Win_set_attr_memory(MPI_Win win, object memory):
    cdef int ierr = MPI_SUCCESS
    if memory is None: return MPI_SUCCESS
    # create keyval for memory object
    global PyMPI_KEYVAL_WIN_MEMORY
    if PyMPI_KEYVAL_WIN_MEMORY == MPI_KEYVAL_INVALID:
        ierr = MPI_Win_create_keyval(MPI_WIN_NULL_COPY_FN,
                                     PyMPI_Win_memory_del,
                                     &PyMPI_KEYVAL_WIN_MEMORY, NULL)
        if ierr: return ierr
    # hold a reference to the object exposing windows memory
    ierr = MPI_Win_set_attr(win, PyMPI_KEYVAL_WIN_MEMORY, <void*>memory)
    if ierr: return ierr
    Py_INCREF(<PyObject*>memory)
    return MPI_SUCCESS
