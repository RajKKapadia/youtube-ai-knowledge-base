if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app="app.main:app",
        reload=True,
        port=8000,
    )
