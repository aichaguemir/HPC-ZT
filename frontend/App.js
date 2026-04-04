import { useState, useEffect } from 'react';
import JobForm from './components/JobForm';
import JobTable from './components/JobTable';
import { fetchJobs } from './fakeApi';

function App() {
  const [refresh, setRefresh] = useState(false);
  const [jobs, setJobs] = useState([]);

  const loadJobs = async () => {
    const res = await fetchJobs();
    setJobs(res.data);
  };

  useEffect(() => {
    loadJobs();
  }, [refresh]);

  return (
    <div className="container">
      <h1>HPC Portal</h1>

      <JobForm refresh={() => setRefresh(!refresh)} />
      <JobTable refreshFlag={refresh} />
    </div>
  );
}

export default App;
