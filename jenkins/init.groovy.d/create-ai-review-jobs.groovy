import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition
import org.jenkinsci.plugins.workflow.job.WorkflowJob


def jenkins = Jenkins.get()
def jobs = [
    'ai-review-build': '/usr/share/jenkins/ref/ai-review/Jenkinsfile.build',
    'ai-review-test': '/usr/share/jenkins/ref/ai-review/Jenkinsfile.test'
]

jobs.each { name, scriptPath ->
    if (jenkins.getItem(name) == null) {
        def job = jenkins.createProject(WorkflowJob, name)
        job.setDescription('Managed AI Review pipeline. Created from the image defaults.')
        job.setDefinition(new CpsFlowDefinition(new File(scriptPath).text, false))
        job.save()
    }
}
