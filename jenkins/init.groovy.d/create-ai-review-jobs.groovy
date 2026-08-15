import jenkins.model.Jenkins
import hudson.model.ParametersDefinitionProperty
import hudson.model.StringParameterDefinition
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition
import org.jenkinsci.plugins.workflow.job.WorkflowJob


def jenkins = Jenkins.get()
def jobs = [
    'ai-review-build': [
        scriptPath: '/usr/share/jenkins/ref/ai-review/Jenkinsfile.build',
        parameters: [
            ['PROJECT_ID', '', 'GitLab project ID'],
            ['MR_IID', '', 'GitLab MR IID'],
            ['SOURCE_BRANCH', '', 'Source branch'],
            ['TARGET_BRANCH', '', 'Target branch'],
            ['COMMIT_SHA', '', 'Commit SHA'],
            ['REPOSITORY_URL', '', 'Git repository URL']
        ]
    ],
    'ai-review-test': [
        scriptPath: '/usr/share/jenkins/ref/ai-review/Jenkinsfile.test',
        parameters: [
            ['PROJECT_ID', '', 'GitLab project ID'],
            ['MR_IID', '', 'GitLab MR IID'],
            ['SOURCE_BRANCH', '', 'Source branch'],
            ['REPOSITORY_URL', '', 'Git repository URL'],
            ['C0_TARGET', '80', 'C0 target'],
            ['C1_TARGET', '70', 'C1 target']
        ]
    ]
]

jobs.each { name, config ->
    def job = jenkins.getItem(name)
    if (job == null) {
        job = jenkins.createProject(WorkflowJob, name)
    }
    job.setDescription('Managed AI Review pipeline. Created from the image defaults.')
    job.setDefinition(new CpsFlowDefinition(new File(config.scriptPath).text, true))
    def parameterDefinitions = config.parameters.collect { parameter ->
        new StringParameterDefinition(parameter[0], parameter[1], parameter[2])
    }
    job.removeProperty(ParametersDefinitionProperty)
    job.addProperty(new ParametersDefinitionProperty(parameterDefinitions))
    job.save()
}
